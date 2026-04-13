from selenium import webdriver
from selenium.webdriver.common.by import By
import pandas as pd
import time

# iniciar navegador
driver = webdriver.Chrome()

driver.get("https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4")

time.sleep(5)  # esperar que cargue

juegos = []

while True:
    productos = driver.find_elements(By.CLASS_NAME, "product")

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

    # intentar botón siguiente
    try:
        siguiente = driver.find_element(By.LINK_TEXT, "Siguiente")
        siguiente.click()
        time.sleep(3)
    except:
        break

df = pd.DataFrame(juegos)
df.to_excel("juegos_ps4.xlsx", index=False)

driver.quit()

print("✅ Excel completo")
