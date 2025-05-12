import time
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from tqdm import tqdm
from bs4 import BeautifulSoup
from html import unescape
import html
import json
import os

def match_case(original, translated):
    """Orijinal metnin büyük/küçük harf durumunu çeviriye uygular."""
    if not original or not translated:
        return translated if translated else ""
    if original.isupper():
        return translated.upper()
    elif original.islower():
        return translated.lower()
    elif original.istitle():
        if len(original) > 1 and original[0].isupper() and original[1:].islower():
            return (translated[0].upper() + translated[1:].lower()) if len(translated) > 0 else ""
    return translated

def translate_with_google(driver, text, delays, webdriver_wait):
    """Google Translate kullanarak metni çevirir."""
    if not text or not isinstance(text, str) or text.strip() == "":
        print("Çevrilecek metin boş veya geçersiz.")
        return ""

    try:
        if len(driver.window_handles) < 2:
            driver.execute_script("window.open('https://translate.google.com/?hl=tr&sl=tr&tl=en', '_blank');")
            WebDriverWait(driver, webdriver_wait).until(EC.number_of_windows_to_be(2))
            time.sleep(delays["general"])

        driver.switch_to.window(driver.window_handles[1])
        input_area = WebDriverWait(driver, webdriver_wait).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[aria-label='Kaynak metin']"))
        )
        driver.execute_script("arguments[0].value = '';", input_area)
        time.sleep(delays["general"])
        input_area.send_keys(text)
        time.sleep(delays["translation"])

        WebDriverWait(driver, webdriver_wait).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "span[jsname='W297wb']"))
        )
        time.sleep(delays["general"])

        translated_text = driver.execute_script("""
            let elements = document.querySelectorAll("span[jsname='W297wb']");
            return Array.from(elements).map(el => el.textContent).join('');
        """)

        if not translated_text or translated_text.strip() == text.strip():
            time.sleep(delays["translation"])
            translated_text = driver.execute_script("""
                let elements = document.querySelectorAll("span[jsname='W297wb']");
                return Array.from(elements).map(el => el.textContent).join('');
            """)

        time.sleep(delays["general"])
        return translated_text

    except TimeoutException:
        print("Google Translate elemanı bulunamadı veya zaman aşımına uğradı.")
        traceback.print_exc()
        return text
    except Exception as e:
        print(f"Çeviri sırasında hata: {e}")
        traceback.print_exc()
        return text
    finally:
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[0])
            time.sleep(delays["general"])

def setup_driver(driver_path):
    """WebDriver'ı başlatır."""
    chrome_options = Options()
    chrome_options.add_argument("--lang=tr-TR")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(driver_path)
    try:
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"WebDriver başlatılırken hata oluştu: {e}")
        traceback.print_exc()
        return None

def login_to_website(driver, email, password):
    """Web sitesine giriş yapar."""
    try:
        driver.get("https://example.com")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//input[@type='email']"))).send_keys(email)
        driver.find_element(By.XPATH, "//input[@type='password']").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        print("Giriş başarılı.")
        time.sleep(3)
    except Exception as e:
        print(f"Giriş sırasında hata: {e}")
        traceback.print_exc()

def preprocess_html_content(html_content):
    """HTML içeriğindeki özel karakterleri çözümler."""
    return unescape(html_content)

def translate_html_text_preserve_tags(html_content, translate_func):
    """HTML içeriğini çevirir, etiketleri korur."""
    soup = BeautifulSoup(html_content, 'html.parser')
    for text_element in soup.find_all(string=True):
        if text_element.strip():
            try:
                resolved_text = preprocess_html_content(text_element)
                translated = translate_func(resolved_text)
                text_element.replace_with(translated)
            except Exception as e:
                print(f"Metin çevirisi sırasında hata: {e}")
                continue
    return html.unescape(str(soup))

def process_product(driver, product_id, delays, webdriver_wait):
    """Ürün bilgilerini işler ve çevirir."""
    base_url = "https://https://example.com/panel/product/{}/edit"
    url = base_url.format(product_id)
    print(f"\nİşleniyor: {url}")
    driver.get(url)
    time.sleep(delays["general"])

    try:
        try:
            server_error = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Server Error')]"))
            )
            if server_error:
                print(f"Sunucu hatası algılandı. Ürün ID {product_id} atlanıyor.")
                return
        except TimeoutException:
            pass

        ckeditor_instance_names = ["editor", "editorL", "editorT"]
        for ckeditor_instance_name in ckeditor_instance_names:
            try:
                is_ready = WebDriverWait(driver, 10).until(
                    lambda drv: drv.execute_script(
                        f"return typeof CKEDITOR !== 'undefined' && CKEDITOR.instances['{ckeditor_instance_name}'] && CKEDITOR.instances['{ckeditor_instance_name}'].instanceReady;"
                    )
                )
                if not is_ready:
                    continue

                product_description = driver.execute_script(
                    f"return CKEDITOR.instances['{ckeditor_instance_name}'].getData();"
                )
                if not product_description.strip():
                    continue

                resolved_description = preprocess_html_content(product_description)
                translated_description = translate_html_text_preserve_tags(resolved_description, lambda text: translate_with_google(driver, text, delays, webdriver_wait))

                if translated_description.strip():
                    driver.execute_script(
                        f"CKEDITOR.instances['{ckeditor_instance_name}'].setData(arguments[0]);",
                        translated_description
                    )
                    time.sleep(delays["general"])
            except TimeoutException:
                print(f"{ckeditor_instance_name} CKEditor yüklenemedi.")
            except Exception as e:
                print(f"{ckeditor_instance_name} CKEditor işlenirken hata oluştu: {e}")
                traceback.print_exc()

        title_field = WebDriverWait(driver, webdriver_wait).until(EC.presence_of_element_located((By.XPATH, "//*[@id='title']")))
        price_field = WebDriverWait(driver, webdriver_wait).until(EC.presence_of_element_located((By.XPATH, "//*[@id='meta_title']")))
        main_field = WebDriverWait(driver, webdriver_wait).until(EC.presence_of_element_located((By.XPATH, "//*[@id='main_desc']")))
        stock_field = WebDriverWait(driver, webdriver_wait).until(EC.presence_of_element_located((By.XPATH, "//*[@id='meta_description']")))
        category_field = WebDriverWait(driver, webdriver_wait).until(EC.presence_of_element_located((By.XPATH, "//*[@id='meta_keywords']")))

        original_title = title_field.get_attribute("value")
        original_price = price_field.get_attribute("value")
        original_main = main_field.get_attribute("value")
        original_stock = stock_field.get_attribute("value")
        original_category = category_field.get_attribute("value")

        translated_title = match_case(original_title, translate_with_google(driver, original_title, delays, webdriver_wait))
        translated_main = match_case(original_main, translate_with_google(driver, original_main, delays, webdriver_wait))
        translated_price = match_case(original_price, translate_with_google(driver, original_price, delays, webdriver_wait))
        translated_stock = match_case(original_stock, translate_with_google(driver, original_stock, delays, webdriver_wait))
        translated_category = match_case(original_category, translate_with_google(driver, original_category, delays, webdriver_wait))

        if translated_price.strip() == translated_stock.strip():
            translated_stock += " - Daha fazla bilgi için."

        if translated_title.strip():
            driver.execute_script("arguments[0].value = arguments[1];", title_field, translated_title)
            time.sleep(delays["general"])
        if translated_main.strip():
            driver.execute_script("arguments[0].value = arguments[1];", main_field, translated_main)
            time.sleep(delays["general"])
        if translated_price.strip():
            driver.execute_script("arguments[0].value = arguments[1];", price_field, translated_price)
            time.sleep(delays["general"])
        if translated_stock.strip():
            driver.execute_script("arguments[0].value = arguments[1];", stock_field, translated_stock)
            time.sleep(delays["general"])
        if translated_category.strip():
            driver.execute_script("arguments[0].value = arguments[1];", category_field, translated_category)
            time.sleep(delays["general"])

        save_button = WebDriverWait(driver, webdriver_wait).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[3]/div/div/div[2]/div/div/form/div[1]/button"))
        )
        save_button.click()
        time.sleep(delays["save"])
        print("Kayıt butonuna tıklandı.")

    except Exception as e:
        print(f"Ürün {product_id} işlenirken hata oluştu: {e}")
        traceback.print_exc()

def load_config(config_path):
    """JSON yapılandırma dosyasını yükler."""
    if not os.path.exists(config_path):
        print(f"Config dosyası bulunamadı: {config_path}")
        return None, None, None

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = json.load(file)

        delays = config["settings"]["delays"]
        links = config["settings"]["links"]
        id_range = config["settings"]["idRange"]

        return delays, links, id_range
    except json.JSONDecodeError as e:
        print(f"Config dosyası hatalı: {e}")
        traceback.print_exc()
        return None, None, None

def main():
    driver_path = "C:\\chromedriver\\chromedriver.exe"
    driver = setup_driver(driver_path)
    if driver is None:
        print("WebDriver başlatılamadı.")
        return

    email = "info@troxgen.com"
    password = "root@1234"

    login_to_website(driver, email, password)

    config_path = "config.json"
    delays, links, id_range = load_config(config_path)

    if delays is None or links is None or id_range is None:
        print("Config dosyası yüklenemedi. Program sonlandırılıyor.")
        return

    webdriver_wait = delays["webdriverWait"]

    print("Delays:", delays)
    print("Links:", links)
    print("ID Range:", id_range)

    start_id = id_range["start"]
    end_id = id_range["end"]

    for product_id in tqdm(range(start_id, end_id - 1, -1), desc="Ürünler İşleniyor"):
        process_product(driver, product_id, delays, webdriver_wait)

    print("\nTüm ürünler işlendi.")
    driver.quit()

if __name__ == "__main__":
    main()
