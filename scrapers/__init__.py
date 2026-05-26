# scrapers/__init__.py
# 作为包的统一出口

from .driver import setup_driver
from .basic_info import get_players_from_stats_page
from .economy import get_economy_data
from .utils import load_config, append_jsonl, load_completed_ids, iter_matches
from .kills import get_match_kills
from .heatmap_utils import get_heatmap_coords, get_paired_cross_coords, get_player_weapons_list

__all__ = [
    'setup_driver',
    'get_players_from_stats_page',
    'get_economy_data',
    'load_config',
    'append_jsonl',
    'load_completed_ids',
    'iter_matches',
    'get_match_kills',
    'get_heatmap_coords',
    'get_paired_cross_coords',
    'get_player_weapons_list'
]