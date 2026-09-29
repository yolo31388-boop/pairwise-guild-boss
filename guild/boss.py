"""帮派BOSS与讨伐系统"""
import random
from dataclasses import dataclass, field

DAILY_CHALLENGE_LIMIT = 3
WEEKLY_CHALLENGE_LIMIT = 10

FULL_PARTICIPATION_TIME = 600.0

DAMAGE_WEIGHT = 1.0
DAMAGE_TAKEN_WEIGHT = 0.5
HEALING_WEIGHT = 0.6

# 血量百分比阈值：>66% 一阶段，33%~66% 二阶段，<=33% 三阶段（狂暴）
PHASE_THRESHOLDS = (0.66, 0.33)
PHASE_SKILLS = {
    1: ("normal_attack",),
    2: ("normal_attack", "whirlwind", "fire_breath"),
    3: ("normal_attack", "whirlwind", "fire_breath", "enrage"),
}

# 时间段刷新系数：高峰期刷得快，深夜慢
TIME_PERIOD_MULTIPLIER = {
    "day": 1.0,
    "prime": 0.7,
    "night": 1.3,
}

# 可在帮派内部交易的通用材料
TRADABLE_MATERIALS = {
    "boss_material_common",
    "boss_scale",
    "boss_fang",
    "boss_hide",
    "essence_rare",
}
# 拾取绑定，不可交易
BOUND_MATERIALS = {
    "boss_soul",
    "boss_heart",
    "legendary_equip",
}


@dataclass
class Boss:
    bid: str
    name: str
    hp: float
    max_hp: float
    phase: int = 1
    spawn_time: float = 0
    guild_id: str = ""
    skills: tuple = field(default_factory=lambda: PHASE_SKILLS[1])
    enraged: bool = False


class GuildBoss:
    def __init__(self):
        self.bosses: dict[str, Boss] = {}
        self.guild_bosses: dict[str, Boss] = {}
        self.next_spawn_time: dict[str, float] = {}
        self.damage: dict[str, float] = {}
        self.damage_taken: dict[str, float] = {}
        self.healing: dict[str, float] = {}
        self.participation_time: dict[str, float] = {}
        self.guild_level: int = 1
        self.daily_kills: dict[str, int] = {}
        self.weekly_kills: dict[str, int] = {}

    # bug1 修复：刷新时间随帮派等级缩短，并受时间段影响；每个帮派独立刷新
    def get_spawn_time(self, guild_level: int, time_period: str = "day") -> float:
        level = max(1, guild_level)
        base = max(1800.0, 21600.0 - level * 1800.0)
        multiplier = TIME_PERIOD_MULTIPLIER.get(time_period, 1.0)
        return base * multiplier

    def spawn_for_guild(self, guild_id: str, guild_level: int,
                        now: float, time_period: str = "day",
                        name: str = "guild_boss"):
        """为指定帮派生成独立BOSS，冷却未到返回None。"""
        if now < self.next_spawn_time.get(guild_id, 0.0):
            return None
        bid = f"{guild_id}:{name}@{now:.0f}"
        max_hp = 1000.0 * guild_level
        boss = Boss(bid=bid, name=name, hp=max_hp, max_hp=max_hp,
                    spawn_time=now, guild_id=guild_id)
        self.bosses[bid] = boss
        self.guild_bosses[guild_id] = boss
        self.next_spawn_time[guild_id] = now + self.get_spawn_time(
            guild_level, time_period)
        return boss

    def _combat_score(self, player: str) -> float:
        return (self.damage.get(player, 0) * DAMAGE_WEIGHT
                + self.damage_taken.get(player, 0) * DAMAGE_TAKEN_WEIGHT
                + self.healing.get(player, 0) * HEALING_WEIGHT)

    def _all_players(self) -> set[str]:
        players = set(self.damage)
        players.update(self.damage_taken)
        players.update(self.healing)
        players.update(self.participation_time)
        return players

    # bug2 修复：个人输出 + 承伤 + 治疗 综合排名
    def get_rank(self, player: str) -> int:
        scores = {p: self._combat_score(p) for p in self._all_players()}
        sorted_players = sorted(scores, key=scores.get, reverse=True)
        return sorted_players.index(player) + 1 if player in sorted_players else 999

    # bug3 修复：按排名阶梯发奖，前10名有特殊奖励
    def get_reward(self, rank: int) -> dict:
        if rank <= 0:
            return {"gold": 0}
        gold = max(50, 1100 - rank * 100)
        reward = {"gold": gold}
        if rank <= 10:
            reward["special"] = "boss_treasure_chest"
            reward["bound_item"] = "medal_top10"
        return reward

    # bug4 修复：积分 = 战斗贡献 + 参与时长，全程参与才拿全额系数
    def get_contribution_score(self, player: str) -> float:
        combat = self._combat_score(player)
        time_in_battle = self.participation_time.get(player, 0)
        ratio = min(1.0, time_in_battle / FULL_PARTICIPATION_TIME)
        multiplier = 0.5 + 0.5 * ratio
        participation_points = time_in_battle * 2.0
        return combat * multiplier + participation_points

    # bug5 修复：按血量阈值切换阶段，解锁新技能，最终阶段狂暴
    def get_phase(self, boss_id: str, hp_pct: float) -> int:
        if hp_pct > PHASE_THRESHOLDS[0] * 100:
            phase = 1
        elif hp_pct > PHASE_THRESHOLDS[1] * 100:
            phase = 2
        else:
            phase = 3
        boss = self.bosses.get(boss_id)
        if boss is not None:
            boss.phase = phase
            boss.skills = PHASE_SKILLS[phase]
            boss.enraged = phase == max(PHASE_SKILLS)
        return phase

    # bug6 修复：每日/每周挑战次数限制
    def can_challenge(self, guild_id: str) -> bool:
        if self.daily_kills.get(guild_id, 0) >= DAILY_CHALLENGE_LIMIT:
            return False
        if self.weekly_kills.get(guild_id, 0) >= WEEKLY_CHALLENGE_LIMIT:
            return False
        return True

    def record_challenge(self, guild_id: str) -> bool:
        if not self.can_challenge(guild_id):
            return False
        self.daily_kills[guild_id] = self.daily_kills.get(guild_id, 0) + 1
        self.weekly_kills[guild_id] = self.weekly_kills.get(guild_id, 0) + 1
        return True

    def reset_daily(self) -> None:
        self.daily_kills.clear()

    def reset_weekly(self) -> None:
        self.weekly_kills.clear()

    # bug7 修复：通用材料可在帮派内交易，稀有/灵魂道具绑定
    def is_tradable(self, item: str) -> bool:
        if item in BOUND_MATERIALS or "bound" in item:
            return False
        if item in TRADABLE_MATERIALS:
            return True
        return item.startswith("boss_material_common")

    def roll_drops(self, rank: int, rng: random.Random | None = None) -> list[str]:
        """掉落混合：部分绑定、部分可在帮派内交易，排名越靠前掉落越好。"""
        r = rng or random
        drops = ["boss_material_common"]
        if rank <= 10:
            drops.append("essence_rare")
        if rank <= 3:
            drops.append("boss_soul")
        if rank == 1 and r.random() < 0.2:
            drops.append("legendary_equip")
        return drops
