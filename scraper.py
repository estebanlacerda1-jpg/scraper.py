import requests
import pandas as pd

url = "https://juegosdigitalesuruguay.com/api/products"

juegos = []

page = 1

while page <= 20:
    print(f"Página {page}")
    
    params = {
        "category": "juegos-digitales-ps4",
        "page": page
    }

    response = requests.get(url, params=params)

    data = response.json()

    productos = data.get("data", [])

    if not productos:
        break

    for p in productos:
        juegos.append({
            "Nombre": p.get("name"),
            "Precio": p.get("price")
        })

    page += 1

df = pd.DataFrame(juegos)
df.to_excel("juegos_ps4.xlsx", index=False)

print("✅ Excel con datos reales")
