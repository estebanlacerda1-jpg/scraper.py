from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pandas as pd
import time

# 🔧 configurar navegador
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

todos = []

print("🔥 SCRAPING PLAYXDIGITAL")

for page in range(1, 50):

    if page == 1:
        url = "https://playxdigital.com/psn/ps4/"
    else:
        url = f"https://playxdigital.com/psn/ps4/page/{page}/"

    print(f"Página {page}")

    driver.get(url)
    time.sleep(4)

    productos = driver.find_elements(By.TAG_NAME, "li")

    for prod in productos:
        texto = prod.text.strip()

        if "$" in texto and len(texto) > 20:

            lineas = texto.split("\n")

            nombre = None
            precio = None

            for l in lineas:
                l = l.strip()

                if not nombre and "$" not in l:
                    nombre = l

                if "$" in l:
                    precio = l

            if nombre and precio:
                todos.append({
                    "Nombre": nombre,
                    "Precio": precio
                })

driver.quit()

# 📊 DataFrame
df = pd.DataFrame(todos)

def limpiar_precio(precio):
    numeros = "".join(c for c in precio if c.isdigit())
    return int(numeros) if numeros else None

df["Precio_num"] = df["Precio"].apply(limpiar_precio)

df = df.dropna(subset=["Precio_num"])
df = df.sort_values("Precio_num")
df = df.drop_duplicates(subset="Nombre", keep="first")

df.to_excel("playxdigital_ps4.xlsx", index=False)

print("✅ LISTO")
