# CI/CD na VM UZP

VM pobiera publiczną gałąź `main` przez HTTPS raz na minutę do terminu odcięcia. Prywatne repozytorium odbiorcze w katalogu domowym użytkownika VM uruchamia CI/CD po otrzymaniu zmiany. Ocena korzysta z projektu w `/opt/solution`. Katalogi `input`, `output` i plik `.env` są wspólne dla kolejnych wydań.

## Pierwsza instalacja

Na komputerze zespołu ustaw `UZP_VM` na login i adres podany przez organizatora. W katalogu projektu uruchom poniższe polecenia. Instalator wymaga istniejących katalogów `/opt/solution/input` i `/opt/solution/output`.

```sh
UZP_VM='login@adres-ip'
ssh "$UZP_VM" 'umask 077 && mkdir -p "$HOME/odwolania2json-bootstrap"'
scp deploy/install.sh deploy/pre-receive deploy/update deploy/install-sync.sh deploy/sync.sh "$UZP_VM:odwolania2json-bootstrap/"
ssh "$UZP_VM" 'bash "$HOME/odwolania2json-bootstrap/install.sh" /opt/solution "$HOME/odwolania2json.git" 2026-11-22T10:00:00Z'
ssh -t "$UZP_VM" 'bash "$HOME/odwolania2json-bootstrap/install-sync.sh" https://github.com/Dymirt/Akta2JSON.git'
git remote add vm "$UZP_VM:odwolania2json.git"
```

Przekaż konfigurację bezpośrednio z lokalnego pliku przez SSH. Poniższa komenda tworzy plik tymczasowy z uprawnieniami `0600` i podmienia konfigurację dopiero po zakończeniu transferu.

```sh
ssh "$UZP_VM" 'set -eu; cd /opt/solution; umask 077; f=$(mktemp .env.XXXXXXXX); trap '\''rm -f -- "$f"'\'' EXIT; cat > "$f"; mv -T "$f" .env' < .env
```

Instalator synchronizacji korzysta z `sudo` przy instalowaniu skryptu i jednostek systemd. Usługa działa jako użytkownik zespołu także po wylogowaniu i po restarcie VM. Timer ma wpisy wyłącznie do 22 listopada 2026 r. godz. 11:00 czasu polskiego. Hook przed aktywacją ponownie sprawdza termin, również jeśli budowanie obrazu rozpoczęło się wcześniej.

## Wysłanie i sprawdzenie wydania

Zatwierdź kod aplikacji, reguły, testy, konfigurację Compose i katalog `deploy/` w lokalnej gałęzi `main`. Wyślij commit do publicznego repozytorium GitHub pod nazwą `origin`. Po zakończeniu budowania i testów porównaj identyfikator aktywnego wydania z lokalnym commitem.

```sh
git push origin main
test "$(git rev-parse main)" = "$(ssh "$UZP_VM" 'readlink /opt/solution/.releases/current')"
test "$(git rev-parse main)" = "$(git ls-remote vm refs/heads/main | cut -f1)"
```

Usługa akceptuje aktualizacje gałęzi przez fast-forward. Stan timera i wynik ostatniej próby na VM pokazują `systemctl status odwolania2json-sync.timer` i `journalctl -u odwolania2json-sync.service -n 50`. Do bezpośredniego prywatnego wdrożenia tego samego commita przez SSH służy `git push vm main`. Obie ścieżki korzystają z tego samego hooka.

Serwer blokuje równoczesne wdrożenia, buduje obraz `hacknation2026-cli:<SHA>` i uruchamia testy bez sieci. Kontener testowy otrzymuje tylko testy i wzorce z danego commita. Po sukcesie serwer sprawdza konfigurację Compose i atomowo przełącza aktywne wydanie. Konfiguracja wskazuje na obraz i katalog wzorców z tego samego commita. `RUN.md` zawiera polecenie do próby z PDF-ami i z rzeczywistym API.

Po błędzie testów popraw kod, zatwierdź poprawkę i ponów push. Jeśli klient utraci połączenie po aktywacji, a Git nie zapisze jeszcze gałęzi, ponów push tego samego commita. Powrót do starszego kodu przeprowadź przez `git revert` i zwykły push do `main`. Zmiany w samych hookach zainstaluj ponownie, kopiując je i uruchamiając instalator jak wyżej.
