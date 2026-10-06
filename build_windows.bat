@echo off
rem Builds dist\Sare\Sare.exe  (run this on Windows with Python 3.12 installed)
python -m venv .venv-build || exit /b 1
call .venv-build\Scripts\activate || exit /b 1
python -m pip install --upgrade pip || exit /b 1
pip install "django>=5.2,<5.3" "django-unfold==0.108.0" openpyxl waitress whitenoise pyinstaller || exit /b 1

python manage.py collectstatic --noinput || exit /b 1

pyinstaller --noconfirm --clean --name Sare ^
  --add-data "templates;templates" --add-data "staticfiles;staticfiles" ^
  --collect-all unfold --collect-data django --collect-submodules django ^
  --collect-submodules inventory --collect-submodules config ^
  --hidden-import waitress --hidden-import whitenoise.middleware ^
  run_sare.py || exit /b 1

echo.
echo Done. Your program is in dist\Sare  (start dist\Sare\Sare.exe)
