"""帮派BOSS与讨伐系统。

修复内容:
1. BOSS 按帮派等级与开放时间段刷新, 每个帮派拥有独立BOSS实例。
2. 伤害排名按 输出 + 承伤 + 治疗 综合计算。
3. 奖励按伤害排名阶梯发放, 前10名有特殊奖励。
4. 讨伐积分按参战时长与贡献度计算, 全程参战才能拿全额。
5. BOSS 按血量阈值进入多阶段, 解锁新技能, 末阶段狂暴。
6. 帮派BOSS有每日/每周挑战次数限制。
7. BOSS掉落区分绑定物品与帮派内可交易物品。
"""
from dataclasses import dataclass, field

DAILY_CHALLENGE_LIMIT = 5
WEEKLY_CHALLENGE_LIMIT = 20

# 全程参战时长(秒), 达到该时长讨伐积分才按全额发放
FULL_PARTICIPATION_TIME = 600.0

# 刷新基础间隔(秒), 帮派每高1级缩短 LEVEL_SPAWN_REDUCTION
BASE_SPAWN_INTERVAL = 7200.0
LEVEL_SPAWN_REDUCTION = 300.0
MIN_SPAWN_INTERVAL = 1800.0

# 开放时间段: (起始秒, 结束秒, 刷新间隔系数), 黄金档刷新更快
SPAWN_WINDOWS = (
    (8 * 3600, 10 * 3600, 1.0),
    (12 * 3600, 14 * 3600, 0.9),
    (19 * 3600, 23 * 3600, 0.8),
)

# 阶段血量阈值(百分比): >66% 一阶段, >33% 二阶段, 否则三阶段(狂暴)
PHASE_HP_THRESHOLDS = (0.66, 0.33)
PHASE_SKILLS = {
    1: ("normal_attack",),
    2: ("normal_attack", "whirlwind", "roar_aoe"),
    3: ("normal_attack", "whirlwind", "roar_aoe", "enrage"),
}
ENRAGE_PHASE = max(PHASE_SKILLS)

TOP_RANK_COUNT = 10

# 可在帮派内部交易的掉落; 其余BOSS掉落默认绑定
GUILD_TRADABLE_ITEMS = frozenset({
    "boss_material_common",
    "boss_material_uncommon",
    "boss_scale_shard",
})
BOUND_ITEMS = frozenset({
    "boss_weapon_rare",
    "boss_armor_epic",
    "boss_heart",
})

@dataclass
class Boss:
    bid: str
    name: str
    hp: float
    max_hp: float
    phase: int = 1
    spawn_time: float = 0
    guild_id: str = ""
    guild_level: int = 1
    enraged: bool = False

    @property
    def hp_pct(self) -> float:
        return self.hp / self.max_hp if self.max_hp else 0.0

    @property
    def skills(self) -> tuple[str, ...]:
        return PHASE_SKILLS.get(self.phase, ())

class GuildBoss:
    def __init__(self):
        self.bosses: dict[str, Boss] = {}
        self.guild_bosses: dict[str, str] = {}  # guild_id -> boss_id, 各帮独立
        self.damage: dict[str, float] = {}  # player -> 个人输出
        self.damage_taken: dict[str, float] = {}  # player -> 承伤
        self.healing: dict[str, float] = {}  # player -> 治疗
        self.participation_time: dict[str, float] = {}  # player -> 参战时长(秒)
        self.daily_kills: dict[str, int] = {}  # guild_id -> 当日击杀数
        self.weekly_kills: dict[str, int] = {}  # guild_id -> 当周击杀数
        self.guild_level: int = 1
        self._spawn_seq = 0

    def is_spawn_open(self, now: float) -> bool:
        """当前时刻是否处于BOSS开放时间段。"""
        seconds_of_day = now % 86400.0
        return any(
            start <= seconds_of_day < end
            for start, end, _ in SPAWN_WINDOWS
        )

    def get_spawn_time(self, guild_level: int, time_slot: int = 0) -> float:
        """刷新间隔: 帮派等级越高越快, 不同开放时间段系数不同。"""
        level = max(1, guild_level)
        interval = BASE_SPAWN_INTERVAL - (level - 1) * LEVEL_SPAWN_REDUCTION
        interval = max(MIN_SPAWN_INTERVAL, interval)
        slot = SPAWN_WINDOWS[time_slot % len(SPAWN_WINDOWS)]
        return interval * slot[2]

    def spawn_boss(self, guild_id: str, guild_level: int = 1,
                   now: float = 0.0, name: str = "guild_boss"):
        """在开放时间段内为指定帮派生成独立BOSS, 非开放时间返回None。"""
        if not self.is_spawn_open(now):
            return None
        self._spawn_seq += 1
        boss_id = f"{guild_id}:boss:{self._spawn_seq}"
        max_hp = 1000.0 * (1.0 + 0.2 * max(0, guild_level - 1))
        boss = Boss(
            bid=boss_id,
            name=name,
            hp=max_hp,
            max_hp=max_hp,
            spawn_time=now,
            guild_id=guild_id,
            guild_level=guild_level,
        )
        self.bosses[boss_id] = boss
        self.guild_bosses[guild_id] = boss_id
        return boss

    def get_guild_boss(self, guild_id: str):
        boss_id = self.guild_bosses.get(guild_id)
        return self.bosses.get(boss_id) if boss_id else None

    def record_combat(self, player: str, damage: float = 0.0,
                      damage_taken: float = 0.0, healing: float = 0.0,
                      participation_time: float = 0.0) -> None:
        self.damage[player] = self.damage.get(player, 0.0) + damage
        self.damage_taken[player] = self.damage_taken.get(player, 0.0) + damage_taken
        self.healing[player] = self.healing.get(player, 0.0) + healing
        self.participation_time[player] = (
            self.participation_time.get(player, 0.0) + participation_time
        )

    def _combat_contribution(self, player: str) -> float:
        # 输出全额计入, 承伤折算坦克贡献, 治疗价值略高于承伤
        return (
            self.damage.get(player, 0.0)
            + 0.2 * self.damage_taken.get(player, 0.0)
            + 0.3 * self.healing.get(player, 0.0)
        )

    def get_rank(self, player: str) -> int:
        players = (
            set(self.damage)
            | set(self.damage_taken)
            | set(self.healing)
            | set(self.participation_time)
        )
        ordered = sorted(players, key=self._combat_contribution, reverse=True)
        return ordered.index(player) + 1 if player in ordered else 999

    def get_reward(self, rank: int) -> dict:
        if rank <= 0:
            return {"gold": 0}
        if rank <= TOP_RANK_COUNT:
            # 阶梯金币: 第1名1000, 每名递减100, 第10名100
            reward = {"gold": 1100 - rank * 100, "elite_reward": "top10_chest"}
            if rank == 1:
                reward["special_reward"] = "champion_trophy"
            return reward
        return {"gold": 50}

    def participation_ratio(self, player: str) -> float:
        return min(
            1.0,
            self.participation_time.get(player, 0.0) / FULL_PARTICIPATION_TIME,
        )

    def is_full_participation(self, player: str) -> bool:
        return self.participation_time.get(player, 0.0) >= FULL_PARTICIPATION_TIME

    def get_contribution_score(self, player: str) -> float:
        # 战斗贡献按参战时长比例折算(全程才全额), 参战本身给基础积分
        combat = self._combat_contribution(player)
        elapsed = self.participation_time.get(player, 0.0)
        return combat * self.participation_ratio(player) + elapsed

    def get_phase(self, boss_id: str, hp_pct: float) -> int:
        if hp_pct > 1.0:
            hp_pct /= 100.0
        if hp_pct > PHASE_HP_THRESHOLDS[0]:
            phase = 1
        elif hp_pct > PHASE_HP_THRESHOLDS[1]:
            phase = 2
        else:
            phase = 3
        boss = self.bosses.get(boss_id)
        if boss is not None:
            boss.phase = phase
            boss.enraged = phase >= ENRAGE_PHASE
        return phase

    def get_skills(self, boss_id: str, hp_pct: float | None = None) -> tuple[str, ...]:
        boss = self.bosses.get(boss_id)
        if hp_pct is not None:
            self.get_phase(boss_id, hp_pct)
        return boss.skills if boss is not None else ()

    def can_challenge(self, guild_id: str) -> bool:
        return (
            self.daily_kills.get(guild_id, 0) < DAILY_CHALLENGE_LIMIT
            and self.weekly_kills.get(guild_id, 0) < WEEKLY_CHALLENGE_LIMIT
        )

    def record_kill(self, guild_id: str) -> bool:
        """击杀成功后记数, 超出每日/每周限制则拒绝。"""
        if not self.can_challenge(guild_id):
            return False
        self.daily_kills[guild_id] = self.daily_kills.get(guild_id, 0) + 1
        self.weekly_kills[guild_id] = self.weekly_kills.get(guild_id, 0) + 1
        return True

    def reset_daily(self) -> None:
        self.daily_kills.clear()

    def reset_weekly(self) -> None:
        self.weekly_kills.clear()

    def is_tradable(self, item: str) -> bool:
        if item in BOUND_ITEMS or item.endswith("_bound"):
            return False
        if item in GUILD_TRADABLE_ITEMS:
            return True
        return item.startswith("boss_material_common")
