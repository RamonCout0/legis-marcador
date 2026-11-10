@echo off
chcp 65001 >nul
title Legis Marcador
cd /d "%~dp0"

echo.
echo  ==============================================
echo    LEGIS MARCADOR
echo    Marcacao automatica das Sessoes Ordinarias
echo  ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo  O Python nao esta instalado neste computador.
  echo  Instale em https://www.python.org/downloads/ ^(marque "Add Python to PATH"^)
  echo  e abra este arquivo de novo.
  echo.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo  Primeira vez: preparando o programa. Isso leva alguns minutos e precisa de internet...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  Nao consegui instalar. Verifique a internet e tente de novo.
    pause
    exit /b 1
  )
)

if not exist .env (
  copy .env.exemplo .env >nul
  echo  Primeira configuracao: vou abrir o arquivo .env no Bloco de Notas.
  echo  Troque os enderecos de exemplo pelos do SEU Legis Videos, salve e feche o Bloco de Notas.
  notepad .env
)

echo  O navegador vai abrir sozinho. Se nao abrir, acesse: http://localhost:8765
echo.
echo  *** MANTENHA ESTA JANELA ABERTA enquanto usa o programa. ***
echo  Para encerrar, feche esta janela.
echo.
.venv\Scripts\python.exe -m app
if errorlevel 1 pause
