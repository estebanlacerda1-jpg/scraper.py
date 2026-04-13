import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

headers = {
    "User-Agent": "Mozilla/5.0"
}

base_url = "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4"

juegos = []
page = 1

while True:
    url = f"{base_url}?page={page}"
    print(f"Página {page}")

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("Error al entrar a la página")
        break

    soup = BeautifulSoup(response.text, "html.parser")

    productos = soup.find_all("div", class_="product-item")

    if not productos:
        print("No hay más productos")
        break

    for p in productos:
        nombre = p.find("h4")
        precio = p.find("span", class_="price")

        if nombre and precio:
            juegos.append({
                "Nombre": nombre.text.strip(),
                "Precio": precio.text.strip()
            })

    page += 1
    time.sleep(2)  # importante para no ser bloqueado

df = pd.DataFrame(juegos)

if df.empty:
    print("⚠️ No se encontraron datos")
else:
    df.to_excel("juegos_ps4.xlsx", index=False)
    print("✅ Excel creado con datos")
