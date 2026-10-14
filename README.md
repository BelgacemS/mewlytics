# Mewlytics

Pokémon VGC tournament results, teams and stats (format M-C). Follow the latest Limitless tournaments with their standings, teams and matches, see which Pokémon are used and how they perform, and add your own local tournaments. Pokémon are also ranked in three tier lists: raw win rates, shrunk win rates, and a Bradley-Terry model that corrects for player skill.

The application is built as microservices on Kubernetes.

Work in progress. Setup and development commands are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Data sources

- Tournament data comes from the public [Limitless API](https://docs.limitlesstcg.com/developer/tournaments). No scraping, and requests stay within the API rate limits.
- Species data (types, base stats, abilities) comes from [PokéAPI](https://pokeapi.co/). It is loaded once into our database and not requested again at runtime, following the PokéAPI fair use policy.

## Disclaimer

This is a student project for a Master's course at Université Paris Cité. It is not affiliated with, endorsed by or sponsored by Nintendo, Creatures, Game Freak, The Pokémon Company or Limitless. Pokémon and related names are trademarks of their respective owners. No official artwork is included in this repository.
