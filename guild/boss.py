"""帮派BOSS与讨伐系统 - 含7个bug"""
from dataclasses import dataclass, field

@dataclass
class Boss:
    bid: str
    name: str
    hp: float
    max_hp: float
    phase: int = 1  # bug5: 无阶段
    spawn_time: float = 0

class GuildBoss:
    def __init__(self):
        self.bosses: dict[str, Boss] = {}
        self.damage: dict[str, float] = {}  # player -> damage
        self.guild_level: int = 1
        self.daily_kills: dict[str, int] = {}  # bug6: 无次数限制

    def get_spawn_time(self, guild_level: int) -> float:
        # bug1: 固定时间
        return 86400.0

    def get_rank(self, player: str) -> int:
        # bug2: 只看总伤害
        sorted_players = sorted(self.damage, key=self.damage.get, reverse=True)
        return sorted_players.index(player) + 1 if player in sorted_players else 999

    def get_reward(self, rank: int) -> dict:
        # bug3: 固定奖励
        return {"gold": 100}

    def get_contribution_score(self, player: str) -> float:
        # bug4: 只看击杀
        return self.damage.get(player, 0)

    def get_phase(self, boss_id: str, hp_pct: float) -> int:
        # bug5: 无阶段
        return 1

    def can_challenge(self, guild_id: str) -> bool:
        # bug6: 无次数限制
        return True

    def is_tradable(self, item: str) -> bool:
        # bug7: 全部绑定
        return False
