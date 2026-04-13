import requests
from bs4 import BeautifulSoup
import pandas as pd

url = "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")

juegos = []

productos = soup.find_all("div", class_="item")

for p in productos:
    try:
        nombre = p.find("h3")
        precio = p.find("span", class_="amount")

        if nombre and precio:
            juegos.append({
                "Nombre": nombre.text.strip(),
                "Precio": precio.text.strip()
            })
    except:
        pass

df = pd.DataFrame(juegos)

df.to_excel("juegos_ps4.xlsx", index=False)

print("✅ Excel con datos")
