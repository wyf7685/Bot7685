# ref: https://github.com/tyql688/WutheringWavesUID/blob/15c975d/WutheringWavesUID/utils/calculate.py

import dataclasses
import functools
from collections import defaultdict
from pathlib import Path
from typing import Literal, NamedTuple, Self, cast

from msgspec import json as msgjson
from pydantic import BaseModel

from ..api.models import Phantom, PhantomAttribute
from ..const import DATA_PATH
from .expr_eval import find_first_matching_expression

CALC_MAP_PATH = DATA_PATH / "calc_map"
FIX_MAX_SCORE = 50

type _PhantomCost = Literal[4, 3, 1]
type _BasicPropsName = Literal["攻击", "攻击%", "生命", "生命%", "防御", "防御%"]
type _CommonPropsName = (
    _BasicPropsName | Literal["暴击", "暴击伤害", "共鸣效率", "治疗效果加成"]
)
type _NormalizedPropsName = _CommonPropsName | Literal["技能伤害加成", "属性伤害加成"]
type _SkillPropsName = Literal[
    "普攻伤害加成",
    "重击伤害加成",
    "共鸣技能伤害加成",
    "共鸣解放伤害加成",
]
type _AttributePropsName = Literal[
    "冷凝伤害加成",
    "热熔伤害加成",
    "导电伤害加成",
    "气动伤害加成",
    "衍射伤害加成",
    "湮灭伤害加成",
]
type _AllPropsName = _CommonPropsName | _SkillPropsName | _AttributePropsName
type _PropsWeightDict = defaultdict[_NormalizedPropsName | str, float]
type _SkillWeight = tuple[float, float, float, float]
_BASIC_PROPS = ("攻击", "生命", "防御")
_SKILLS = ("普攻", "重击", "共鸣技能", "共鸣解放")
_ATTRS = ("冷凝", "热熔", "导电", "气动", "衍射", "湮灭")


class _GradeLevel(NamedTuple):
    c: float
    b: float
    a: float
    s: float
    ss: float
    sss: float


class _PropsGrade(NamedTuple):
    c1: _GradeLevel
    c3: _GradeLevel
    c4: _GradeLevel


class _ScoreMax(NamedTuple):
    c1: float
    c3: float
    c4: float


class _ValidGradeProps(BaseModel):
    valid_s: list[_AllPropsName]
    valid_a: list[_AllPropsName]
    valid_b: list[_AllPropsName]


def _check_conditions(ctx: dict[str, object], condition_path: Path) -> str | None:
    if not condition_path.exists():
        return None
    expressions = msgjson.decode(condition_path.read_text(encoding="utf-8"))
    return find_first_matching_expression(ctx, expressions)


@dataclasses.dataclass
class PhantomCalcResult:
    phantom: Phantom
    score: float
    level: str

    @functools.cached_property
    def name(self) -> str:
        return self.phantom.phantomProp.name

    type _SumResultKey = _CommonPropsName | Literal["属性伤害加成"] | _SkillPropsName
    type SumResult = dict[_SumResultKey, float]

    def sum(self) -> SumResult:
        result: dict[str, float] = defaultdict(float)
        result["攻击"] = result["生命"] = result["防御"] = 0.0

        for prop in self.phantom.get_props():
            name = prop.attributeName
            if name in _BASIC_PROPS and "%" in prop.attributeValue:
                name += "%"
            value = float(prop.attributeValue.removesuffix("%"))
            if name.startswith(_ATTRS):
                name = "属性伤害加成"
            result[name] += value

        return cast(PhantomCalcResult.SumResult, result)


class PhantomCalc(BaseModel):
    name: str
    main_props: dict[int, _PropsWeightDict]
    sub_props: _PropsWeightDict
    max_main_props: dict[str, list[_NormalizedPropsName]]  # key: "1.1"/"3.1"/"4.1"
    skill_weight: _SkillWeight = (0, 0, 0, 0)
    grade: _ValidGradeProps
    total_grade: _GradeLevel
    props_grade: _PropsGrade
    score_max: _ScoreMax

    @classmethod
    def get(cls, role_id: int, ctx: dict[str, object]) -> Self:
        if not (char_dir := CALC_MAP_PATH / str(role_id)).exists():
            char_dir = CALC_MAP_PATH / "default"

        calc_json = _check_conditions(ctx, char_dir / "condition.json")
        path = char_dir / (calc_json or "calc.json")
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def calc_phantom_prop_score(
        self, prop: PhantomAttribute, cost: _PhantomCost
    ) -> float:
        props_weight = self.main_props[cost] if prop.is_main else self.sub_props
        percentage = "%" if "%" in prop.attributeValue else ""
        name = prop.attributeName
        value = float(prop.attributeValue.removesuffix("%"))

        if name in _BASIC_PROPS:
            score = props_weight[name + percentage] * value
        elif (prefix := name.removesuffix("伤害加成")) in (_SKILLS + _ATTRS):
            if prefix in _SKILLS:
                skill_weight = self.skill_weight[_SKILLS.index(prefix)]
                score = props_weight["技能伤害加成"] * skill_weight * value
            else:
                score = props_weight["属性伤害加成"] * value
        else:
            score = props_weight[name] * value

        return score

    def get_phantom_level(self, cost: _PhantomCost, percent_score: float) -> str:
        props_grade = self.props_grade[[1, 3, 4].index(cost)]
        values: list[tuple[str, float]] = list(props_grade._asdict().items())
        for level, score in sorted(values, key=lambda x: x[1], reverse=True):
            if percent_score >= score:
                return level
        return "c"

    def calc_phantom_score(self, phantom: Phantom) -> PhantomCalcResult:
        phantom_score = sum(
            self.calc_phantom_prop_score(prop, phantom.cost)
            for prop in phantom.get_props()
        )
        percent_score = phantom_score / self.score_max[[1, 3, 4].index(phantom.cost)]
        score = round(percent_score * FIX_MAX_SCORE, 1)
        level = self.get_phantom_level(phantom.cost, percent_score).upper()
        return PhantomCalcResult(phantom, score, level)
