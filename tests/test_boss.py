"""帮派BOSS与讨伐系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guild.boss import GuildBoss, Boss

class TestSpawnTime:
    def test_higher_guild_level_faster_spawn(self):
        gb = GuildBoss()
        t1 = gb.get_spawn_time(1)
        t10 = gb.get_spawn_time(10)
        assert t10 < t1

class TestRankingByContribution:
    def test_ranking_includes_more_than_damage(self):
        gb = GuildBoss()
        gb.damage = {"p1": 1000, "p2": 100}
        # 应该有承伤/治疗等维度
        assert hasattr(gb, "damage_taken")
        gb.damage_taken = {"p1": 0, "p2": 5000}
        rank_p2 = gb.get_rank("p2")
        assert rank_p2 <= 2

class TestRewardByRank:
    def test_top_rank_better_reward(self):
        gb = GuildBoss()
        r1 = gb.get_reward(1)
        r10 = gb.get_reward(10)
        assert r1["gold"] > r10["gold"]

class TestContributionScore:
    def test_contribution_includes_participation(self):
        gb = GuildBoss()
        assert hasattr(gb, "participation_time")
        gb.damage["p1"] = 0
        gb.participation_time = {"p1": 300}
        score = gb.get_contribution_score("p1")
        assert score > 0

class TestBossPhases:
    def test_boss_has_multiple_phases(self):
        gb = GuildBoss()
        gb.bosses["b1"] = Boss("b1", "dragon", 1000, 1000)
        p1 = gb.get_phase("b1", 90)
        p2 = gb.get_phase("b1", 30)
        assert p2 > p1

class TestChallengeLimit:
    def test_daily_challenge_limit(self):
        gb = GuildBoss()
        gb.daily_kills["g1"] = 5
        assert gb.can_challenge("g1") == False

class TestTradableItems:
    def test_some_items_are_guild_tradable(self):
        gb = GuildBoss()
        assert gb.is_tradable("boss_material_common") == True
