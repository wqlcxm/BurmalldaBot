import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass
class TgBot:
    token: str
    admin_id: int  # Добавили поле

@dataclass
class Config:
    tg_bot: TgBot

def load_config() -> Config:
    load_dotenv()
    return Config(
        tg_bot=TgBot(
            token=os.getenv("BOT_TOKEN"),
            admin_id=int(os.getenv("ADMIN_ID"))
        )
    )