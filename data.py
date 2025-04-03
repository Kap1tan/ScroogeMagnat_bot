from utils import load_referral_data, load_users_data, load_json_data, save_json_data
from config import CREDITED_REFERRALS_FILE, STARS_PER_REFERRAL

referral_data = load_referral_data()
users_data = load_users_data()

# Загружаем список пользователей, для которых уже был засчитан реферал,
# и преобразуем его в множество для быстрого поиска.
credited_data = load_json_data(CREDITED_REFERRALS_FILE)
credited_referrals = set(credited_data.get("credited", []))

# Загружаем текущее количество звёзд за реферала
stars_config = load_json_data("data/config.json")
stars_per_referral = stars_config.get("stars_per_referral", STARS_PER_REFERRAL)

def save_credited_referrals():
    from utils import save_json_data
    save_json_data(CREDITED_REFERRALS_FILE, {"credited": list(credited_referrals)})

def save_stars_config():
    from utils import save_json_data
    save_json_data("data/config.json", {"stars_per_referral": stars_per_referral})
