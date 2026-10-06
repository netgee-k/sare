"""Starts Sare like a normal desktop program: database set-up, local web server, browser."""
import io
import os
import socket
import sys
import threading
import webbrowser

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

HOST = os.environ.get("SARE_HOST", "127.0.0.1")   # set SARE_HOST=0.0.0.0 to share on your network
PORT = int(os.environ.get("SARE_PORT", "8000"))


def local_host():
    return "127.0.0.1" if HOST in ("0.0.0.0", "") else HOST


def port_in_use():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((local_host(), PORT)) == 0


def open_browser(url):
    if not os.environ.get("SARE_NO_BROWSER"):
        webbrowser.open(url)


def first_run_setup():
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    quiet = io.StringIO()
    call_command("migrate", interactive=False, verbosity=0)
    call_command("setup_roles", stdout=quiet)

    User = get_user_model()
    if not User.objects.filter(is_superuser=True).exists():
        name, password = os.environ.get("SARE_ADMIN_USER"), os.environ.get("SARE_ADMIN_PASSWORD")
        if name and password:
            User.objects.create_superuser(name, "", password)
        else:
            print("\nFirst run: create the administrator account.\n", flush=True)
            call_command("createsuperuser")


def main():
    url = f"http://{local_host()}:{PORT}/"
    if port_in_use():
        print("Sare is already running - opening it in your browser.", flush=True)
        open_browser(url)
        return

    import django
    django.setup()
    from django.conf import settings

    print("Starting Sare Inventory System...", flush=True)
    first_run_setup()

    from waitress import serve
    from config.wsgi import application

    print(f"\n  Sare is running at {url}", flush=True)
    print(f"  Your data is stored in: {settings.DATABASES['default']['NAME']}", flush=True)
    print("  Keep this window open while you work. Close it to stop Sare.\n", flush=True)
    threading.Timer(1.5, open_browser, args=(url,)).start()
    serve(application, host=HOST, port=PORT, threads=8, ident="Sare")


if __name__ == "__main__":
    main()
