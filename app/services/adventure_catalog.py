"""v5에서 실제 사용 가능한 보상. 70종 후보는 획득 목록에 넣지 않는다."""

from typing import Any


def item(
    code: str, name: str, slot: str, asset: str = "", rarity: str = "COMMON", starter: bool = False
) -> dict[str, Any]:
    return {"code": code, "name": name, "slot": slot, "asset": asset, "rarity": rarity, "starter": starter}


CATALOG = [
    item("explorer-hat", "모험가의 모자", "hat", "equipment-hat.webp"),
    item("explorer-bag", "여행자의 가방", "bag", "equipment-bag.webp"),
    item("magic-syringe", "별빛 주사기", "hand", "equipment-syringe.webp", "RARE"),
    item("crystal-sword", "별빛 수정검", "hand", "equipment-sword.webp", "RARE"),
    item("explorer-boots", "모험가의 신발", "shoes", "equipment-boots.webp"),
    item("night", "별빛 정원", "background"),
    item("dawn", "새벽 정원", "background", rarity="RARE"),
    item("lantern", "모험가의 등불", "ornament", "room-decor-v1/lantern.webp"),
    item("flowers", "반짝 꽃 화분", "ornament", "room-decor-v1/plant.webp", "RARE"),
    item("material", "성장의 조각", "material"),
    item("meadow", "초록 정원", "background", starter=True),
    item("room-basic-bed", "기본 원목 침대", "bed", "room-decor-v1/basic-bed.webp", starter=True),
    item("room-star-bed", "별빛 침대", "bed", "room-decor-v1/star-bed.webp"),
    item("room-basic-desk", "기본 컴퓨터 책상", "computer", "room-decor-v1/basic-desk.webp", starter=True),
    item("room-crystal-desk", "수정빛 컴퓨터 책상", "computer", "room-decor-v1/crystal-desk.webp", "RARE"),
    item("room-basic-chair", "기본 나무 의자", "chair", "room-decor-v1/basic-chair.webp", starter=True),
    item("room-cloud-chair", "구름 라운지 의자", "chair", "room-decor-v1/cloud-chair.webp", "RARE"),
    item("room-basic-light", "기본 스탠드 조명", "light", "room-decor-v1/basic-light.webp", starter=True),
    item("room-moon-light", "달빛 스탠드", "light", "room-decor-v1/moon-light.webp"),
]
BY_CODE = {entry["code"]: entry for entry in CATALOG}
BASIC_ROOM = {
    "bed": "room-basic-bed",
    "computer": "room-basic-desk",
    "chair": "room-basic-chair",
    "light": "room-basic-light",
    "background": "meadow",
}
EQUIPMENT_SLOTS = {"hat", "bag", "hand", "shoes"}
ROOM_SLOTS = {"bed", "computer", "chair", "light", "background", "ornament"}
