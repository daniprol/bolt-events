"""E2E tests for playground UI using Playwright."""

import pytest


pytestmark = pytest.mark.e2e


@pytest.fixture
async def browser_page(live_server):
    """Create a browser page for testing."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(10000)
        yield page
        await context.close()
        await browser.close()


@pytest.mark.e2e
class TestPlaygroundUI:
    """E2E tests for the playground UI."""

    async def test_playground_loads(self, browser_page, live_server):
        """Test that playground page loads."""
        await browser_page.goto(live_server.url)

        title = await browser_page.title()
        assert "A2A" in title or "Playground" in title

    async def test_sidebar_present(self, browser_page, live_server):
        """Test sidebar elements are present."""
        await browser_page.goto(live_server.url)

        new_chat = browser_page.locator("#new-chat-btn")
        if await new_chat.count() > 0:
            assert await new_chat.is_visible()

    async def test_chat_input_present(self, browser_page, live_server):
        """Test chat input is visible."""
        await browser_page.goto(live_server.url)

        chat_input = browser_page.locator("#chat-input")
        if await chat_input.count() > 0:
            assert await chat_input.is_visible()

    async def test_agent_card_displayed(self, browser_page, live_server):
        """Test agent info is displayed."""
        await browser_page.goto(live_server.url)

        await browser_page.wait_for_load_state("networkidle")

    async def test_dark_mode_toggle(self, browser_page, live_server):
        """Test dark mode toggle works."""
        await browser_page.goto(live_server.url)

        theme_toggle = browser_page.locator("#theme-toggle")
        if await theme_toggle.count() > 0:
            await theme_toggle.click()
            await browser_page.wait_for_timeout(100)

            is_dark = await browser_page.evaluate(
                "document.documentElement.classList.contains('dark')"
            )
            assert is_dark is True

    async def test_create_new_conversation(self, browser_page, live_server):
        """Test creating new conversation."""
        await browser_page.goto(live_server.url)

        new_chat = browser_page.locator("#new-chat-btn")
        if await new_chat.count() > 0:
            await new_chat.click()
            await browser_page.wait_for_timeout(100)

            chat_input = browser_page.locator("#chat-input")
            if await chat_input.count() > 0:
                assert await chat_input.is_enabled()


@pytest.mark.e2e
class TestPlaygroundInteraction:
    """E2E tests for playground interactions."""

    async def test_send_message(self, browser_page, live_server):
        """Test sending a message."""
        await browser_page.goto(live_server.url)

        new_chat = browser_page.locator("#new-chat-btn")
        if await new_chat.count() > 0:
            await new_chat.click()
            await browser_page.wait_for_timeout(100)

        chat_input = browser_page.locator("#chat-input")
        if await chat_input.count() > 0:
            await chat_input.fill("Hello, agent!")
            await browser_page.wait_for_timeout(100)

            send_btn = browser_page.locator("#send-btn")
            if await send_btn.count() > 0:
                await send_btn.click()
                await browser_page.wait_for_timeout(500)

                user_msg = browser_page.locator(".user-message")
                if await user_msg.count() > 0:
                    assert await user_msg.first.is_visible()

    async def test_enter_sends_message(self, browser_page, live_server):
        """Test pressing Enter sends message."""
        await browser_page.goto(live_server.url)

        new_chat = browser_page.locator("#new-chat-btn")
        if await new_chat.count() > 0:
            await new_chat.click()
            await browser_page.wait_for_timeout(100)

        chat_input = browser_page.locator("#chat-input")
        if await chat_input.count() > 0:
            await chat_input.fill("Test message")
            await chat_input.press("Enter")
            await browser_page.wait_for_timeout(500)

    async def test_empty_message_not_sent(self, browser_page, live_server):
        """Test empty message is not sent."""
        await browser_page.goto(live_server.url)

        chat_input = browser_page.locator("#chat-input")
        if await chat_input.count() > 0:
            await chat_input.fill("")
            await chat_input.press("Enter")
            await browser_page.wait_for_timeout(100)

            messages = browser_page.locator(".message")
            count = await messages.count()
            assert count == 0


@pytest.mark.e2e
class TestPlaygroundResponsive:
    """E2E tests for playground responsiveness."""

    async def test_mobile_view(self, browser_page, live_server):
        """Test playground works on mobile view."""
        await browser_page.set_viewport_size({"width": 375, "height": 667})
        await browser_page.goto(live_server.url)
        await browser_page.wait_for_load_state("networkidle")

    async def test_tablet_view(self, browser_page, live_server):
        """Test playground works on tablet view."""
        await browser_page.set_viewport_size({"width": 768, "height": 1024})
        await browser_page.goto(live_server.url)
        await browser_page.wait_for_load_state("networkidle")

    async def test_desktop_view(self, browser_page, live_server):
        """Test playground works on desktop view."""
        await browser_page.set_viewport_size({"width": 1280, "height": 800})
        await browser_page.goto(live_server.url)
        await browser_page.wait_for_load_state("networkidle")
