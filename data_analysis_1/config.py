from pathlib import Path
#路径
DATA_PATH = Path("原数据路径")
OUT_DIR = Path("文件输出路径")
FIG_DIR = Path("图表输出路径")
#自动创建输出目录
OUT_DIR.mkdir(exist_ok=True)
FIG_DIR.mkdir(exist_ok=True)
#经济劣势阈值
DISADV_RATIO = 0.75

#高价值武器（主分析）—— 保留用于武器价格映射的参照，但实际改用价格表
HIGH_VALUE_WEAPONS = [
    "awp",
    "ak-47", "ak47",
    "m4a4",
    "m4a1", "m4a1-s", "m4a1 silenced",
    "sg 553", "sg553",
    "aug",
    "galil",
    "famas",
    "desert eagle", "deagle"
]
#低投入买枪类型
LOW_BUY_TYPES = [
    "eco",
    "semi eco", "semi-eco",
    "semi buy", "semibuy",
    "force buy", "force-buy"
]
#武器价格映射表
WEAPON_PRICES = {
    # === 手枪 (Pistols) ===
    "glock-18": 200,
    "usp-s": 200,
    "p2000": 200,
    "p250": 300,
    "dualberettas": 300,
    "dual_berettas": 300,
    "cz75-auto": 500,
    "five-seven": 500,
    "tec-9": 500,
    "revolver": 600,
    "r8_revolver": 600,
    "deagle": 700,
    "desert_eagle": 700,
    
    # === 冲锋枪 (SMGs) ===
    "mac-10": 1050,
    "mp9": 1250,
    "mp7": 1500,
    "mp5-sd": 1500,
    "pp-bizon": 1400,
    "ump-45": 1200,
    "p90": 2350,
    
    # === 步枪 (Rifles) ===
    "galil": 1800,
    "galilar": 1800,
    "famas": 2050,
    "ak47": 2700,
    "m4a1_silencer": 2900,
    "m4a4": 2900,
    "sg553": 3000,
    "aug": 3300,
    "ssg08": 1700,
    "awp": 4750,
    "scar20": 5000,
    "g3sg1": 5000,
    
    # === 重型武器 (Heavy) ===
    "nova": 1050,
    "sawed_off": 1100,
    "mag7": 1300,
    "mag-7": 1300,
    "xm1014": 2000,
    "negev": 1700,
    "m249": 5200,
    
    # === 装备 (Equipment) ===
    "defuser": 400,
    "vest": 650,
    "vesthelm": 1000,
    "zeus": 200,
    
    # === 投掷物 (Grenades) ===
    "decoy": 50,
    "flashbang": 200,
    "hegrenade": 300,
    "smokegrenade": 300,
    "molotov": 400,
    "incgrenade": 600,
    
    # === 近战武器 (Melee) ===
    "knife": 0,
    "bayonet": 0,
    "butterfly_knife": 0,
    "karambit": 0,
    "m9_bayonet": 0,
}
DEFAULT_WEAPON_PRICE = 1000