from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.webkit.launch(headless=False)   # ⭐ 改这里
    page = browser.new_page()

    page.goto("https://zhaopin.meituan.com/web/position/detail?jobUnionId=4214730848")

    page.wait_for_timeout(5000)
    print(page.title())

    browser.close()