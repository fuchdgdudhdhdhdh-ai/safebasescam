import os
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from database import Session, Person, CheckLog, AdminAction, normalize_query

router = Router()
MASTER_ID = int(os.environ["ADMIN_ID"])

class Flow(StatesGroup):
    add_target = State()
    add_description = State()
    delete_target = State()

def is_master(user_id):
    return user_id == MASTER_ID

def keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 Добавить скамера", callback_data="sb:add:scam")],
        [InlineKeyboardButton(text="🛡 Добавить администратора базы", callback_data="sb:add:admin")],
        [InlineKeyboardButton(text="🗑 Удалить запись", callback_data="sb:delete")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="sb:stats")],
    ])

@router.message(Command("admin"))
async def show_admin(message: Message):
    if not is_master(message.from_user.id):
        await message.answer("⛔ Доступ разрешён только главному администратору.")
        return
    await message.answer("🛡 SafeBase — главная админ-панель", reply_markup=keyboard())

@router.callback_query(F.data.startswith("sb:"))
async def actions(callback: CallbackQuery, state: FSMContext):
    if not is_master(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    if parts[1] == "add":
        await state.update_data(kind=parts[2])
        await state.set_state(Flow.add_target)
        await callback.message.answer("Отправьте @username или числовой Telegram ID:")
    elif parts[1] == "delete":
        await state.set_state(Flow.delete_target)
        await callback.message.answer("Введите @username или ID записи для удаления:")
    elif parts[1] == "stats":
        async with Session() as s:
            total = await s.scalar(select(func.count(Person.id))) or 0
            scams = await s.scalar(select(func.count(Person.id)).where(Person.kind == "scam")) or 0
            admins = await s.scalar(select(func.count(Person.id)).where(Person.kind == "admin")) or 0
            checks = await s.scalar(select(func.count(CheckLog.id))) or 0
        await callback.message.answer(
            f"📊 SafeBase\nВсего записей: {total}\nСкамеров: {scams}\nАдминистраторов базы: {admins}\nПроверок: {checks}"
        )
    await callback.answer()

@router.message(Flow.add_target)
async def add_target(message: Message, state: FSMContext):
    if not is_master(message.from_user.id):
        await state.clear()
        return
    try:
        key, username, telegram_id = normalize_query(message.text or "")
    except ValueError:
        await message.answer("Неверный формат. Укажите @username или числовой ID.")
        return
    async with Session() as s:
        if await s.scalar(select(Person).where(Person.key == key)):
            await message.answer("Эта запись уже существует.")
            await state.clear()
            return
    await state.update_data(key=key, username=username, telegram_id=telegram_id)
    await state.set_state(Flow.add_description)
    await message.answer("Введите описание или отправьте точку (.) без описания:")

@router.message(Flow.add_description)
async def add_description(message: Message, state: FSMContext):
    if not is_master(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    description = "" if (message.text or "").strip() == "." else (message.text or "").strip()[:1500]
    async with Session() as s:
        s.add(Person(key=data["key"], username=data["username"], telegram_id=data["telegram_id"],
                     kind=data["kind"], description=description, added_by=message.from_user.id))
        s.add(AdminAction(actor_id=message.from_user.id, action="add_" + data["kind"], target=data["key"]))
        await s.commit()
    await state.clear()
    await message.answer("✅ Запись добавлена.")

@router.message(Flow.delete_target)
async def delete_target(message: Message, state: FSMContext):
    if not is_master(message.from_user.id):
        await state.clear()
        return
    try:
        key, _, _ = normalize_query(message.text or "")
    except ValueError:
        await message.answer("Неверный формат.")
        return
    async with Session() as s:
        person = await s.scalar(select(Person).where(Person.key == key))
        if person is None:
            await message.answer("Запись не найдена.")
        else:
            await s.delete(person)
            s.add(AdminAction(actor_id=message.from_user.id, action="delete", target=key))
            await s.commit()
            await message.answer("✅ Запись удалена.")
    await state.clear()
