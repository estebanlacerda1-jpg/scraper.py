import requests
from bs4 import BeautifulSoup
import pandas as pd

base_url = "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4"

juegos = []
page = 1
max_paginas = 20

headers = {
    "User-Agent": "Mozilla/5.0"
}

while page <= max_paginas:
    print(f"Página {page}")
    
    url = f"{base_url}?page={page}"
    response = requests.get(url, headers=headers)

    soup = BeautifulSoup(response.text, "html.parser")

    productos = soup.find_all("div", class_="product")

    if not productos:
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

df = pd.DataFrame(juegos)

df.to_excel("juegos_ps4.xlsx", index=False)

print("✅ Excel creado con datos")
