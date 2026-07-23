from database.db_core import format_username

BOT_WATERMARK = 'Отправлено через @BurmalldaBot'


def build_video_caption(
    *,
    title: str | None = None,
    views: int | None = None,
    likes: int | None = None,
    author_username: str | None = None,
    show_details: bool = True,
    header: str | None = None,
) -> str:
    """Собирает подпись под видео. Водяной знак бота всегда в конце."""
    parts: list[str] = []

    if show_details:
        if header:
            parts.append(header)
        if title:
            parts.append(f'🎬 <b>{title}</b>')
        if likes is not None:
            parts.append(f'❤️ Лайков: {likes}')
        if views is not None:
            parts.append(f'👁️ Просмотров: {views}')
        if author_username:
            parts.append(f'👤 {format_username(author_username)}')

    parts.append(BOT_WATERMARK)
    return '\n\n'.join(parts)
