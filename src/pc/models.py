"""Modelli input/output del builder deterministico."""
from dataclasses import dataclass, field


@dataclass
class CharacterDraft:
    name: str
    method: str
    campaign_type: str
    abilities: dict
    race: str
    class_: str = field(metadata={"alias": "class"})
    race_bonus_ability: str | None = None
    favored_class_bonus: str = "hp"
    skills: dict = field(default_factory=dict)
    feats: list = field(default_factory=list)
    traits: list = field(default_factory=list)
    equipment: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        if "class" in data:
            data["class_"] = data.pop("class")
        return cls(**data)
