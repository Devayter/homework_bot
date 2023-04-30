"""Бот для проверки статуса домашнего задания, отправленного на проверку."""
import logging
import os
import time
from http import HTTPStatus
from logging import StreamHandler
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv

from custom_errors import EmptyResponseFromApiError, NotAvaliableError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(
    __file__ + '.log', maxBytes=50000000, backupCount=5, encoding='utf-8'
)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(lineno)s'
    '- %(message)s'
)
handler.setFormatter(formatter)

handler_stream = StreamHandler()
logger.addHandler(handler_stream)
handler_stream.setFormatter(formatter)

load_dotenv()

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
    tokens_tuple = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID),
    )
    availability = True
    for token_name, token_value in tokens_tuple:
        if not token_value:
            logger.critical(f'Отсутствует токен {token_name}')
            availability = False
    if availability is False:
        error_message = 'Отсутствует переменная окружения.'
        logger.critical(error_message)
        raise ValueError(error_message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат, определяемый переменной окружения.
    TELEGRAM_CHAT_ID. Принимает на вход два параметра: экземпляр класса Bot и
    строку с текстом сообщения.
    """
    logger.debug('Отправка сообщения')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError(message) as error:
        logger.error(error, exc_info=True)
        return False
    logger.debug(f'Eспешно отправлено сообщение "{message}"')
    return True


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передается временная метка. В случае
    успешного запроса должна вернуть ответ API, приведя его из формата JSON
    к типам данных Python.
    """
    api_data_dict = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    logger.debug('Запрос к {url} с параметрами '
                 '{params}'.format(**api_data_dict))
    try:
        response = requests.get(**api_data_dict)
    except requests.RequestException:
        raise ConnectionError(
            '{url}, {headers}, {params}'.format(**api_data_dict)
        )
    if response.status_code != HTTPStatus.OK:
        raise NotAvaliableError('Api недоступен')

    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации.
    В качестве параметра. функция получает ответ API, приведенный к типам
    данных Python.
    """
    logger.debug('Проверка ответа API')
    if not isinstance(response, dict):
        raise TypeError('Ответ API не приведен к типу данных Python')
    # если делать проверку ключа через if, то не проходит проверку pytest
    try:
        response['homeworks']
    except EmptyResponseFromApiError('Отсутствует "homeworks" в ответе API'):
        return None
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Ответ API под ключом "homeworks" не в виде списка')
    return homeworks


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха, функция возвращает подготовленную для
    отправки в Telegram строку, содержащую один из вердиктов словаря
    HOMEWORK_VERDICTS.
    """
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
    except KeyError as error:
        raise (f'Ошибка {error}: Отсутствует ожидаемый ключ в ответе Api')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Неожиданное принятое значение статуса - {homework_status}'
        )
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0
    current_report = dict()
    previous_report = dict()
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            homeworks = check_response(api_answer)
            if homeworks:
                current_report['message'] = parse_status(homeworks[0])
            else:
                current_report['message'] = 'Нет новых статусов'
            if previous_report != current_report:
                if send_message(bot, current_report['message']):
                    previous_report = current_report.copy()
                    timestamp = api_answer.get('current_date', 0)
            else:
                logger.debug('Нет новых статусов')
        except EmptyResponseFromApiError as error:
            logger.error(error, exc_info=True)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            current_report['message'] = message
            logger.error(message)
            if previous_report != current_report:
                previous_report = current_report.copy()
                send_message(bot, current_report['message'])
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
