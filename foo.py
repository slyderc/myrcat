import requests

response = requests.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
    "grant_type": "fb_exchange_token",
    "client_id": "990597318664907",
    "client_secret": "59ba04a77eb04414d9f18dc2bb134091",
    "fb_exchange_token": "EAAOE8WlLYssBO3BZBFnxXT3bFxlvvHUEAo9DKL16Ylsdn1DArGb78GAbmHvGq5B7GCVPbIpYV88jTOuFZAABTtUVayIYSCZAQgxqhEguegciDKopJOeZA0yOZBZBEya0bZBSfEZC3jFdorH4ZAEcsT7Ot5dvgdZAmcMGEnrpPptmlMNGlkArYRGUEkYSYnyNY7GZC3JTqqegGvwZCSD62ZAQies7K7Er9NQ3ZBZA1N0QamQTmhf1wZDZD"})

print(response.json())

