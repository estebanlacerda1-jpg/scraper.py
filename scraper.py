from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import pandas as pd
import time

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

url = "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4"
driver.get(url)

time.sleep(5)

juegos = []

while True:
    productos = driver.find_elements(By.CLASS_NAME, "product-item")

    for p in productos:
        try:
            nombre = p.find_element(By.TAG_NAME, "h4").text
            precio = p.find_element(By.CLASS_NAME, "price").text

            juegos.append({
                "Nombre": nombre,
                "Precio": precio
            })
        except:
            pass

    try:
        siguiente = driver.find_element(By.LINK_TEXT, "Siguiente")
        siguiente.click()
        time.sleep(5)
    except:
        break

driver.quit()

df = pd.DataFrame(juegos)

if df.empty:
    print("⚠️ No se encontraron datos")
else:
    df.to_excel("juegos_ps4.xlsx", index=False)
    print("✅ Excel creado")
