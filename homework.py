import logging
import os
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv
from telegram import Bot

from castom_errors import NotAvalibleError, SendMessageError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(
    'my_logger.log', maxBytes=50000000, backupCount=5
)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(lineno)s'
    '- %(message)s'
)
handler.setFormatter(formatter)

load_dotenv()

CHECK_PERIOD = 600

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения.
    Если отсутствует хотя бы одна переменная окружения — продолжать работу
    бота нет смысла.
    """
    if not (PRACTICUM_TOKEN or TELEGRAM_TOKEN or TELEGRAM_CHAT_ID):
        error_message = 'Отсутствует переменная окружения.'
        logger.critical(error_message)
        raise ValueError(error_message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат, определяемый переменной окружения.
    TELEGRAM_CHAT_ID. Принимает на вход два параметра: экземпляр класса Bot и
    строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except SendMessageError:
        logger.error('Ошибка при отправке сообщения.', exc_info=True)

    logger.debug('Сообщение успешно отправлено.')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передается временная метка. В случае
    успешного запроса должна вернуть ответ API, приведя его из формата JSON
    к типам данных Python.
    """
    url = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
    headers = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
    payload = {'from_date': timestamp}
    try:
        response = requests.get(url, headers=headers, params=payload)
    except requests.RequestException:
        logger.error('Ошибка при запросе Api', exc_info=True)
    try:
        response.json()['homeworks'][0]
    except IndexError:
        logger.error('индекс списка вне допустимого диапазона ', exc_info=True)
    if response.status_code != HTTPStatus.OK:
        raise NotAvalibleError('Api недоступен')
    check_response(response.json())
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации.
    В качестве параметра. функция получает ответ API, приведенный к типам
    данных Python.
    """
    if type(response) != dict:
        raise TypeError('ответ API не приведен к типу данных Python')
    if 'homeworks' not in response.keys():
        raise KeyError('Отсутствует ожидаемый ключ "homeworks" в ответе API')
    if type(response['homeworks']) != list:
        raise TypeError(
            'Ответ API под ключом "homeworks" приходит не в виде списка'
        )


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха, функция возвращает подготовленную для
    отправки в Telegram строку, содержащую один из вердиктов словаря
    HOMEWORK_VERDICTS.
    """
    try:
        homework_name = homework['homework_name']
        verdict = HOMEWORK_VERDICTS[homework['status']]
    except KeyError:
        logger.error('Отсутствует ожидаемый ключ в ответе Api', exc_info=True)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            message = parse_status(api_answer['homeworks'][0])
            send_message(bot, message)
        except Exception as error:
            logger.error(f'Сбой в работе программы: {error}')
        finally:
            time.sleep(CHECK_PERIOD)
            timestamp = int(time.time()) - CHECK_PERIOD


if __name__ == '__main__':
    main()
