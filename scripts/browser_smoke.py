"""Run against isolated test API on 8000 and Vite on 3000; no paid calls."""
from pathlib import Path
import sys
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
response = httpx.get("http://127.0.0.1:8000/api/test-mode", timeout=5)
if response.status_code != 200 or response.json().get("isolated_browser_test") is not True:
    raise SystemExit("Refusing to run: start backend.tests.browser_server, not the paid production API")
ROOT.joinpath("runtime").mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width":1440,"height":1000})
    errors = []
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto("http://127.0.0.1:3000")
    page.get_by_role("button",name="История проектов",exact=False).click()
    expect(page.get_by_text("Пока нет проектов.",exact=False)).to_be_visible()
    page.get_by_role("button",name="Сравнение документов",exact=True).click()
    page.get_by_role("button",name="Контрольный пример",exact=True).click()
    page.get_by_role("button",name="Начать анализ",exact=True).click()
    expect(page.get_by_text("Результаты сравнения",exact=True)).to_be_visible(timeout=30000)
    page.get_by_role("button",name="Доказательства",exact=True).first.click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.get_by_label("Решение аналитика").select_option("confirmed")
    page.get_by_label("Комментарий").fill("Проверено браузерным тестом")
    page.get_by_role("button",name="Сохранить решение",exact=True).click()
    expect(page.get_by_text("Решение сохранено",exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).not_to_be_visible()
    with page.expect_download() as download:
        page.get_by_role("link",name="Markdown",exact=True).click()
    assert "Проверено браузерным тестом" in Path(download.value.path()).read_text()
    page.get_by_role("button",name="Все проекты",exact=True).click()
    expect(page.locator(".history-card")).to_have_count(1)
    expect(page.locator(".history-card")).to_contain_text("Завершён")
    expect(page.locator(".history-card")).to_contain_text("проверено выводов: 1")
    page.get_by_label("Поиск проектов").fill("несуществующее имя")
    expect(page.get_by_text("Проекты по этому фильтру не найдены.")).to_be_visible()
    page.get_by_label("Поиск проектов").fill("")
    page.screenshot(path=str(ROOT/"runtime/history-desktop.png"),full_page=True)
    page.reload()
    page.get_by_role("button",name="История проектов",exact=False).click()
    expect(page.locator(".history-card")).to_have_count(1)
    page.set_viewport_size({"width":375,"height":812})
    page.emulate_media(reduced_motion="reduce")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "history overflow"
    page.screenshot(path=str(ROOT/"runtime/history-mobile.png"),full_page=True)
    page.get_by_role("button",name="Открыть проект",exact=False).click()
    expect(page.get_by_text("Результаты сравнения",exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "results overflow"
    page.get_by_role("button",name="Доказательства",exact=True).first.click()
    expect(page.get_by_role("dialog")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "dialog overflow"
    page.screenshot(path=str(ROOT/"runtime/evidence-mobile.png"),full_page=True)
    page.keyboard.press("Escape")
    page.set_viewport_size({"width":812,"height":375})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "landscape overflow"
    page.set_viewport_size({"width":1440,"height":1000})
    page.get_by_text("Загрузить другой комплект документов",exact=True).click()
    names = ["Север", "Юг", "Восток", "Запад", "Центр", "Склад", "Доставка", "Страхование", "Транспорт", "Планирование", "Качество", "Упаковка", "Архив", "Снабжение", "Договоры", "Возвраты", "Логистика", "Таможня"]
    text = "\n".join(f"1.{i}. Отдел {name}:\n1.{i}.1. Проверяет реестр направления {name}." for i,name in enumerate(names,1))
    for index,name in enumerate(["новая-логистика-до.txt","новая-логистика-после.txt"]):
        page.locator('input[type="file"]').nth(index).set_input_files({"name":name,"mimeType":"text/plain","buffer":text.encode()})
    page.get_by_role("button",name="Загрузить комплект",exact=True).click()
    page.get_by_role("button",name="Начать анализ",exact=True).click()
    expect(page.get_by_text("Результаты сравнения",exact=True)).to_be_visible(timeout=30000)
    expect(page.locator(".map-row")).to_have_count(15)
    page.get_by_role("button",name="Далее",exact=True).click()
    expect(page.locator(".map-row")).to_have_count(3)
    page.get_by_role("button",name="Все выводы",exact=False).click()
    page.get_by_role("button",name="Следующие функции",exact=True).click()
    page.get_by_role("button",name="Следующие функции",exact=True).click()
    expect(page.locator(".register-row")).to_have_count(6)
    assert not errors, errors
    browser.close()
    print("PASS: analysis, citations, review, export, history, filters, reload, mobile, landscape; no JS errors")
