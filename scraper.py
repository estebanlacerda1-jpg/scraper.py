import requests
from bs4 import BeautifulSoup
import pandas as pd

query = "juegos digitales ps4 uruguay precio"
url = f"https://www.google.com/search?q={query}"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")

juegos = []

resultados = soup.find_all("h3")

for r in resultados:
    juegos.append({
        "Nombre": r.text,
        "Precio": "Consultar"
    })

df = pd.DataFrame(juegos)
df.to_excel("juegos_ps4.xlsx", index=False)

print("✅ Excel generado")
