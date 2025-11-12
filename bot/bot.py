import os
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv
import numpy as np

load_dotenv()

class DataSearchBot:
    def __init__(self, data_file='data.csv'):
        self.data_file = data_file
        self.df = self.load_data()
        self.user_searches = {}

    def load_data(self):
        try:
            df = pd.read_csv(self.data_file)
            if 'name' in df.columns:
                df['name_lower'] = df['name'].str.lower().str.strip()
            return df
        except FileNotFoundError:
            print(f"Файл {self.data_file} не найден!")
            return pd.DataFrame()
        except Exception as e:
            print(f"Ошибка при загрузке данных: {e}")
            return pd.DataFrame()

    def search_by_name(self, name):
        if self.df.empty:
            return None, "empty_df"

        name_lower = name.lower().strip()
        exact_match = self.df[self.df['name_lower'] == name_lower]

        if not exact_match.empty:
            return exact_match, "exact"

        partial_match = self.df[self.df['name_lower'].str.contains(name_lower, na=False)]

        if not partial_match.empty:
            return partial_match.sort_values(by = ['rating', 'price'], ascending = [False, True]), "partial"

        return None, "not_found"

    def search_by_speciality_and_metro(self, speciality, metro=None):
        if self.df.empty:
            return pd.DataFrame()

        speciality_lower = speciality.lower().strip()
        results = self.df.copy()

        if 'speciality' in self.df.columns:
            def search_in_specialities(speciality_field):
                if pd.isna(speciality_field):
                    return False
                field_str = str(speciality_field).lower()
                return speciality_lower in field_str

            speciality_mask = results['speciality'].apply(search_in_specialities)
            results = results[speciality_mask]

        if results.empty:
            return results

        if metro and metro.strip():
            metro_lower = metro.lower().strip()
            metro_columns = [
                'clinic_1_metro_sber', 'clinic_2_metro_sber', 'clinic_3_metro_sber',
                'clinic_1_metro_prod', 'clinic_2_metro_prod', 'clinic_3_metro_prod'
            ]

            metro_mask = pd.Series([False] * len(results), index=results.index)

            for col in metro_columns:
                if col in results.columns:
                    if not results[col].isna().all():
                        col_mask = results[col].fillna('').astype(str).str.lower().str.contains(metro_lower, na=False)
                        metro_mask = metro_mask | col_mask

            if metro_mask.any():
                results = results[metro_mask].sort_values(by = ['rating', 'price'], ascending = [False, True])
            else:
                return pd.DataFrame()

        return results

    def save_user_search(self, user_id, results):
        self.user_searches[user_id] = {
            'results': results,
            'current_page': 0,
            'timestamp': pd.Timestamp.now()
        }

    def get_user_results_page(self, user_id, page=0, results_per_page=5):
        if user_id not in self.user_searches:
            return None, None, None

        user_data = self.user_searches[user_id]
        results = user_data['results']
        total_results = len(results)
        total_pages = (total_results + results_per_page - 1) // results_per_page

        if page >= total_pages:
            page = total_pages - 1
        if page < 0:
            page = 0

        start_idx = page * results_per_page
        end_idx = min(start_idx + results_per_page, total_results)

        page_results = results.iloc[start_idx:end_idx]
        user_data['current_page'] = page

        return page_results, page, total_pages

bot_data = DataSearchBot()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
Привет! Это бот для поиска и аналитики врачей города Москвы. 
Чтобы начать поиск по ФИО, введи /search. Для поиска по специальности введи /speciality.
    """

    keyboard = [
        [InlineKeyboardButton("Поиск по ФИО", callback_data="start_search")],
        [InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")],
        [InlineKeyboardButton("Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
Команды:
/start - начать работу
/help - показать эту справку
/search - поиск по ФИО врача
/speciality - поиск по специальности и метро
    """

    keyboard = [
        [InlineKeyboardButton("Поиск по ФИО", callback_data="start_search")],
        [InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")],
        [InlineKeyboardButton("Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_text = """
Введи ФИО интересующего тебя врача. 
Пример: Иванов Иван Иванович

Можно вводить:
- Полное ФИО: Иванов Иван Иванович
- Частично: Иванов
- Фамилию и имя: Иванов Иван
    """
    await update.message.reply_text(search_text, parse_mode='Markdown')


async def speciality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_text = """
Поиск врачей по специальности и метро

Введите данные в формате:
Специальность, станция метро

Пример: "Терапевт, Новослободская"
    """
    await update.message.reply_text(search_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.message.from_user.id

    if not user_message.strip():
        await update.message.reply_text("Пожалуйста, введите данные для поиска")
        return

    if ',' in user_message:
        parts = user_message.split(',', 1)
        speciality = parts[0].strip()
        metro = parts[1].strip() if len(parts) > 1 else None

        results = bot_data.search_by_speciality_and_metro(speciality, metro)

        if results.empty:
            metro_text = f" и метро '{metro}'" if metro else ""
            await update.message.reply_text(
                f"Врачи по специальности '{speciality}'{metro_text} не найдены.\n\nПопробуйте изменить запрос или уточнить специальность."
            )
            return

        bot_data.save_user_search(user_id, results)
        await show_results_page(update, context, user_id, 0)

    else:
        results, search_type = bot_data.search_by_name(user_message)

        if search_type == "not_found":
            keyboard = [
                [InlineKeyboardButton("Повторный поиск по ФИО", callback_data="start_search")],
                [InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")],
                [InlineKeyboardButton("Помощь", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Информация не найдена. \nПопробуйте изменить запрос или уточнить ФИО.",
                reply_markup=reply_markup
            )
            return

        if search_type == "exact":
            result_text = format_detailed_result(results.iloc[0], bot_data.df)
            keyboard = [
                [InlineKeyboardButton("Поиск по ФИО", callback_data="start_search")],
                [InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")],
                [InlineKeyboardButton("Показать всех", callback_data="show_all")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                photo_path = f"doctor_photo{np.random.randint(5)}.jpg"
                with open(photo_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=result_text,
                        reply_markup=reply_markup
                    )
            except FileNotFoundError:
                await update.message.reply_text(
                    result_text,
                    reply_markup=reply_markup
                )

        elif search_type == "partial":
            bot_data.save_user_search(user_id, results)
            await show_results_page(update, context, user_id, 0)

async def show_results_page(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, page: int):
    results, current_page, total_pages = bot_data.get_user_results_page(user_id, page)

    if results is None or results.empty:
        if update.callback_query:
            await update.callback_query.message.reply_text("Данные не найдены. Выполните повторный поиск")
        else:
            await update.message.reply_text("Данные не найдены. Выполните повторный поиск")
        return

    message_text = f"Найдено совпадений: {len(bot_data.user_searches[user_id]['results'])}\n\n"

    for i, (index, row) in enumerate(results.iterrows(), start=page * 5 + 1):
        message_text += f"{i}. {row['name']}\n"

        if 'speciality' in row and pd.notna(row['speciality']):
            speciality_value = row['speciality']

            if isinstance(speciality_value, (list, tuple)):
                speciality_str = ', '.join(map(str, speciality_value))
            elif isinstance(speciality_value, str) and (',' in speciality_value or ';' in speciality_value):
                speciality_str = speciality_value.replace(';', ',').replace('|', ',')
            else:
                speciality_str = str(speciality_value)

            message_text += f"Специальность: {speciality_str}\n"
        else:
            message_text += "Специальность: не указана\n"

        if 'experience' in row and pd.notna(row['experience']):
            message_text += f"Опыт работы: {row['experience']} лет\n"

        if 'price' in row and pd.notna(row['price']):
            message_text += f"Цена приёма: {row['price']} руб.\n"

        if 'rating' in row and pd.notna(row['rating']):
            message_text += f"Рейтинг: {row['rating']}/5.0\n"

        metro = set()
        metro_columns = ['clinic_1_metro_sber', 'clinic_2_metro_sber', 'clinic_3_metro_sber',
                         'clinic_1_metro_prod', 'clinic_2_metro_prod', 'clinic_3_metro_prod']

        for col in metro_columns:
            if col in row and pd.notna(row[col]):
                metro.add(str(row[col]))

        if metro:
            message_text += f"Метро: {', '.join(metro)}\n"
        else:
            message_text += "Метро: нет данных\n"

        message_text += "\n"

    message_text += f"Страница {current_page + 1} из {total_pages}"

    keyboard = []

    pagination_buttons = []
    if current_page > 0:
        pagination_buttons.append(InlineKeyboardButton("Назад", callback_data=f"page_{current_page - 1}"))

    pagination_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="current_page"))

    if current_page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("Вперед", callback_data=f"page_{current_page + 1}"))

    if pagination_buttons:
        keyboard.append(pagination_buttons)

    for i, (index, row) in enumerate(results.iterrows(), start=page * 5 + 1):
        doctor_button = [InlineKeyboardButton(
            f"Подробнее {i} - {row['name'].split()[0]}",
            callback_data=f"detail_{index}"
        )]
        keyboard.append(doctor_button)

    action_buttons = [
        InlineKeyboardButton("Поиск по имени", callback_data="start_search"),
        InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")
    ]
    keyboard.append(action_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    try:
        if data == "help":
            help_text = """
Команды:
/start - начать работу
/help - показать эту справку
/search - поиск по ФИО врача
/speciality - поиск по специальности и метро

Как использовать:
- Для поиска по ФИО: введите фамилию врача или полное ФИО
- Для поиска по специальности: введите "специальность, метро"
            """
            keyboard = [
                [InlineKeyboardButton("Поиск по ФИО", callback_data="start_search")],
                [InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")],
                [InlineKeyboardButton("Назад", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

        elif data == "start_search":
            search_text = """
Введи ФИО интересующего тебя врача. 
Пример: Иванов Иван Иванович

Можно вводить:
- Полное ФИО: Иванов Иван Иванович
- Частично: Иванов
- Фамилию и имя: Иванов Иван
            """
            await query.message.reply_text(search_text)

        elif data == "speciality_search":
            search_text = """
Поиск врачей по специальности и метро

Введите данные в формате:
Специальность, станция метро

Пример: "Терапевт, Новослободская"
            """
            await query.message.reply_text(search_text)

        elif data == "main_menu":
            welcome_text = """
Привет! Это бот для поиска и аналитики врачей города Москвы. 
Чтобы начать поиск по ФИО, введи /search. Для поиска по специальности введи /speciality.
            """

            keyboard = [
                [InlineKeyboardButton("Поиск по ФИО", callback_data="start_search")],
                [InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")],
                [InlineKeyboardButton("Помощь", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(welcome_text, reply_markup=reply_markup)

        elif data == "show_all":
            bot_data.save_user_search(user_id, bot_data.df)
            await query.message.reply_text("Показаны все врачи из базы данных:")
            await show_results_page(update, context, user_id, 0)

        elif data.startswith("page_"):
            page = int(data.split("_")[1])
            await show_results_page(update, context, user_id, page)

        elif data.startswith("detail_"):
            index = int(data.split("_")[1])
            if user_id in bot_data.user_searches:
                results = bot_data.user_searches[user_id]['results']
                if index in results.index:
                    result_text = format_detailed_result(results.loc[index], bot_data.df)

                    keyboard = [
                        [InlineKeyboardButton("К результатам",
                                              callback_data=f"page_{bot_data.user_searches[user_id]['current_page']}")],
                        [InlineKeyboardButton("Поиск по ФИО", callback_data="start_search")],
                        [InlineKeyboardButton("Поиск по специальности", callback_data="speciality_search")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    try:
                        photo_path = f"doctor_photo{np.random.randint(5)}.jpg"
                        with open(photo_path, 'rb') as photo:
                            await query.message.reply_photo(
                                photo=photo,
                                caption=result_text,
                                reply_markup=reply_markup
                            )
                    except FileNotFoundError:
                        await query.message.reply_text(
                            result_text,
                            reply_markup=reply_markup
                        )
        elif data == "current_page":
            pass

    except Exception as e:
        print(f"Ошибка в button_handler: {e}")
        await query.message.reply_text("Произошла ошибка. Попробуйте снова.")

def format_detailed_result(row, df):
    result = "Подробная информация:\n\n"
    result += f"ФИО: {row['name']}\n"

    metro = set()
    metro_columns = ['clinic_1_metro_sber', 'clinic_2_metro_sber', 'clinic_3_metro_sber',
                     'clinic_1_metro_prod', 'clinic_2_metro_prod', 'clinic_3_metro_prod']

    for col in metro_columns:
        if col in row and pd.notna(row[col]):
            metro.add(str(row[col]))

    if metro:
        result += f"Метро: {', '.join(metro)}\n"
    else:
        result += "Метро: Нет данных\n"

    if 'speciality' in row and pd.notna(row['speciality']):
        speciality_value = row['speciality']
        if isinstance(speciality_value, (list, tuple)):
            result += f"Специальность: {', '.join(map(str, speciality_value))}\n"
        else:
            result += f"Специальность: {str(speciality_value)}\n"
    else:
        result += "Специальность: Нет данных\n"

    if 'experience' in row and pd.notna(row['experience']):
        result += f"Опыт работы: {row['experience']} лет\n"
    else:
        result += "Опыт работы: Нет данных\n"

    if 'rating' in row and pd.notna(row['rating']):
        result += f"Взвешенный рейтинг: {row['rating']}/5.0 \n"

    result += "\n"

    result += "СберЗдоровье:\n"
    price_s = row['price_sber'] if 'price_sber' in row and pd.notna(row['price_sber']) else "нет данных"
    rating_s = row['rating_sber'] if 'rating_sber' in row and pd.notna(row['rating_sber']) else "нет данных"

    if 'link_sber' in row and pd.notna(row['link_sber']):
        result += f"Цена: {price_s}\n"
        result += f"Рейтинг: {rating_s}\n"
        result += f"Ссылка: {row['link_sber']}\n"
    else:
        result += f"Цена: {price_s}\n"
        result += f"Рейтинг: {rating_s}\n"
    result += "\n"

    result += "ПроДокторов:\n"
    price_p = row['price_prod'] if 'price_prod' in row and pd.notna(row['price_prod']) else "нет данных"
    rating_p = row['rating_prod'] if 'rating_prod' in row and pd.notna(row['rating_prod']) else "нет данных"

    if 'link_prod' in row and pd.notna(row['link_prod']):
        result += f"Цена: {price_p}\n"
        result += f"Рейтинг: {rating_p}\n"
        result += f"Ссылка: {row['link_prod']}\n"
    else:
        result += f"Цена: {price_p}\n"
        result += f"Рейтинг: {rating_p}\n"
    result += "\n"

    result += "Сравнение с рынком:\n"

    current_specialities = set()
    if 'speciality' in row and pd.notna(row['speciality']):
        if isinstance(row['speciality'], (list, tuple)):
            current_specialities = set(map(str, row['speciality']))
        else:
            current_specialities = {str(row['speciality'])}

    market_doctors = df.copy()

    if current_specialities:
        def has_matching_speciality(doctor_row):
            if 'speciality' not in doctor_row or pd.isna(doctor_row['speciality']):
                return False
            if isinstance(doctor_row['speciality'], (list, tuple)):
                doctor_specialities = set(map(str, doctor_row['speciality']))
            else:
                doctor_specialities = {str(doctor_row['speciality'])}

            return bool(current_specialities & doctor_specialities)

        market_mask = market_doctors.apply(has_matching_speciality, axis=1)
        market_doctors = market_doctors[market_mask]


    if pd.notna(row['price']): price_current = row['price']
    else: price_current = None
    if pd.notna(market_doctors['price'].mean()): price_market = market_doctors['price'].mean()
    else: price_market = None

    if price_current and price_market and len(market_doctors) != 1:
        if price_current > price_market:
            result += f"💔 Цена выше рынка специалистов на {price_current - price_market:.1f} руб\n"
        elif price_current < price_market:
            result += f"💚 Цена ниже рынка специалистов на {price_market - price_current:.1f} руб\n"
        else:
            result += "Цена совпадает с средним значением по рынку специалистов\n"
    else:
        result += "Нет данных для сравнения цен\n"

    if pd.notna(row['rating']): rating_current = row['rating']
    else: rating_current = None
    if pd.notna(market_doctors['rating'].mean()): rating_market = market_doctors['rating'].mean()
    else: rating_market = None

    if rating_current and rating_market and len(market_doctors) != 1:
        if rating_current > rating_market:
            result += f"💚 Рейтинг выше рынка специалистов на {rating_current - rating_market:.1f}\n"
        elif rating_current < rating_market:
            result += f"💔 Рейтинг ниже рынка специалистов на {rating_market - rating_current:.1f}\n"
        else:
            result += "Рейтинг совпадает со средним значением по рынку специалистов\n"
    else:
        result += "Нет данных для сравнения рейтингов\n"

    if current_specialities and not market_doctors.empty and len(market_doctors) != 1:
        result += f"\nСравнение с {len(market_doctors)} врачами аналогичных специальностей\n"

    return result

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')

    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не найден в переменных окружения!")
        return


    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("speciality", speciality_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.add_error_handler(error_handler)

    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()