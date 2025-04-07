from utils import load_referral_data, load_users_data, load_json_data, save_json_data
from config import CREDITED_REFERRALS_FILE, STARS_PER_REFERRAL, REQUIRED_CHANNELS_FILE
from config import CAPTCHA_PASSED_REFERRALS_FILE

referral_data = load_referral_data()
users_data = load_users_data()

# Загружаем список пользователей, прошедших капчу
captcha_data = load_json_data(CAPTCHA_PASSED_REFERRALS_FILE)
captcha_passed_referrals = set(captcha_data.get("passed", []))

def save_captcha_passed_referrals():
    """
    Сохраняет список пользователей, прошедших капчу
    """
    save_json_data(CAPTCHA_PASSED_REFERRALS_FILE, {"passed": list(captcha_passed_referrals)})

# Загружаем список пользователей, для которых уже был засчитан реферал,
# и преобразуем его в множество для быстрого поиска.
credited_data = load_json_data(CREDITED_REFERRALS_FILE)
credited_referrals = set(credited_data.get("credited", []))

# Загружаем текущее количество звёзд за подписку
stars_config = load_json_data("data/config.json")
stars_per_referral = stars_config.get("stars_per_referral", STARS_PER_REFERRAL)

# Загружаем список активных промокодов
promocodes_data = load_json_data("data/promocodes.json")
promocodes = promocodes_data.get("promocodes", {})

# Загружаем список обязательных каналов для подписки
required_channels_data = load_json_data(REQUIRED_CHANNELS_FILE)
required_channels = required_channels_data.get("channels", [])

def save_credited_referrals():
    from utils import save_json_data
    save_json_data(CREDITED_REFERRALS_FILE, {"credited": list(credited_referrals)})

def save_stars_config():
    from utils import save_json_data
    save_json_data("data/config.json", {"stars_per_referral": stars_per_referral})

def save_promocodes():
    from utils import save_json_data
    save_json_data("data/promocodes.json", {"promocodes": promocodes})

def save_required_channels():
    from utils import save_json_data
    save_json_data(REQUIRED_CHANNELS_FILE, {"channels": required_channels})

def update_stars_per_referral():
    """
    Обновляет значение звезд за реферала из файла конфигурации
    """
    global stars_per_referral
    stars_config = load_json_data("data/config.json")
    stars_per_referral = stars_config.get("stars_per_referral", STARS_PER_REFERRAL)
    return stars_per_referral