import requests
from bs4 import BeautifulSoup
import pandas as pd

base_url = "https://juegosdigitalesuruguay.com/categorias/juegos-digitales-ps4"

juegos = []
page = 1

while True:
    url = f"{base_url}?page={page}"
    response = requests.get(url)

    if response.status_code != 200:
        break

    soup = BeautifulSoup(response.text, "html.parser")

    nombres = soup.find_all("h4")
    precios = soup.find_all("span", class_="price")

    if not nombres:
        break

    for nombre, precio in zip(nombres, precios):
        juegos.append({
            "Nombre": nombre.text.strip(),
            "Precio": precio.text.strip()
        })

    page += 1

df = pd.DataFrame(juegos)
df.to_excel("juegos_ps4.xlsx", index=False)
