import functools
from dataclasses import dataclass
from typing import Any

from ..api.models import Phantom, RoleDetail
from .phantom import PhantomCalc, PhantomCalcResult
from .sonata import WavesSonata, get_sonata_detail

type _CalcContext = dict[str, Any]


@dataclass
class RolePhantomCalcResult:
    phantoms: list[PhantomCalcResult | None]

    @functools.cached_property
    def total(self) -> float:
        return sum(p.score for p in self.phantoms if p)


class WuwaCalc:
    role_detail: RoleDetail
    ctx: _CalcContext

    def __init__(self, role_detail: RoleDetail) -> None:
        self.role_detail = role_detail
        self.ctx = {}
        self.prepare_phantom()

    def _add_value(self, name: str, value: str) -> None:
        if name not in self.ctx:
            self.ctx[name] = value
            return

        old = float(str(self.ctx[name]).removesuffix("%"))
        new = float(value.removesuffix("%"))
        self.ctx[name] = f"{old + new:.1f}"

    @functools.cached_property
    def phantom_equip(self) -> list[Phantom | None] | None:
        return (
            self.role_detail.phantomData
            and self.role_detail.phantomData.equipPhantomList
        )

    def sum_phantom_value(self, phantom: Phantom) -> None:
        for prop in phantom.get_props():
            is_percentage = "%" in prop.attributeValue
            name = prop.attributeName
            if is_percentage and name in ("攻击", "生命", "防御"):
                name = f"{name}%"

            self._add_value(name, prop.attributeValue)

    def prepare_phantom(self) -> None:
        self.ctx = {"ph_detail": (ph_detail := []), "echo_id": 0}
        if not self.phantom_equip:
            return

        if self.phantom_equip[0]:
            self.ctx["echo_id"] = self.phantom_equip[0].phantomProp.phantomId

        sonata_result: dict[WavesSonata, set[int]] = {}
        for phantom in filter(None, self.phantom_equip):
            self.sum_phantom_value(phantom)
            if sonata := get_sonata_detail(phantom.fetterDetail.name):
                sonata_result.setdefault(sonata, set()).add(
                    phantom.phantomProp.phantomId
                )

        for sonata, ids in sonata_result.items():
            num = len(ids)
            ph_detail.append({"ph_num": num, "ph_name": sonata.name})
            if num >= 2:
                self.ctx["ph"] = sonata.name
                self._add_value(sonata.set["2"].effect, sonata.set["2"].param[0])

    def calc_phantom(self) -> RolePhantomCalcResult:
        if not self.phantom_equip:
            return RolePhantomCalcResult([])

        calc = PhantomCalc.get(self.role_detail.role.roleId, self.ctx)
        return RolePhantomCalcResult(
            [p and calc.calc_phantom_score(p) for p in self.phantom_equip]
        )
