import random
from io import BytesIO
from pathlib import Path

from meme_generator import MemeArgsModel, MemeArgsType, ParserOption, add_meme
from meme_generator.exception import TextOverLength
from pil_utils import BuildImage
from pil_utils.types import PointsType, PosTypeInt, SizeType
from pydantic import Field

img_dir = Path(__file__).parent / "images"
total_num = len(list(img_dir.iterdir()))

help_text = f"图片编号，范围为 1~{total_num}"
parser_options = [
    ParserOption(
        names=["-n", "--number"],
        default=0,
        help_text=help_text,
    )
]


class Model(MemeArgsModel):
    number: int = Field(0, description=help_text)


params: list[tuple[PosTypeInt, SizeType, PointsType]] = [
    ((275, 770), (410, 220), ((0, 84), (388, 15), (430, 220), (42, 280))),
    ((290, 760), (400, 240), ((0, 0), (400, 0), (400, 240), (0, 240))),
    ((230, 10), (610, 300), ((0, 0), (610, 0), (585, 300), (25, 300))),
    ((290, 700), (560, 320), ((0, 80), (510, 20), (560, 300), (50, 360))),
    ((-30, 50), (590, 350), ((0, 90), (480, -20), (540, 270), (60, 380))),
    ((315, 610), (600, 480), ((0, 140), (510, 0), (600, 340), (70, 480))),
    ((540, 50), (550, 340), ((40, 0), (520, 90), (480, 340), (0, 250))),
]


def goldenglow_holdsign(
    _: list[BuildImage],
    texts: list[str],
    args: Model,
) -> BytesIO:
    text = texts[0]
    num = args.number if 1 <= args.number <= total_num else random.randint(1, total_num)

    loc, (width, height), points = params[num - 1]
    frame = BuildImage.open(img_dir / f"{num}.png")
    text_img = BuildImage.new("RGBA", (width, height))
    padding = 10
    try:
        text_img.draw_text(
            (padding, padding, width - padding, height - padding),
            text,
            max_fontsize=180,
            min_fontsize=60,
            allow_wrap=True,
            lines_align="center",
            spacing=10,
            fontname="FZShaoEr-M11S",
            fill="#3b0b07",
        )
    except ValueError as err:
        raise TextOverLength(text) from err
    frame.paste(text_img.perspective(points), loc, alpha=True)
    return frame.save_png()


add_meme(
    "goldenglow_holdsign",
    goldenglow_holdsign,  # pyright:ignore[reportArgumentType]
    min_texts=1,
    max_texts=1,
    default_texts=["YOU!"],
    args_type=MemeArgsType(
        args_model=Model,
        args_examples=[Model(number=1)],
        parser_options=parser_options,
    ),
    keywords=["澄闪举牌", "猪猪举牌"],
)
