::
:: This only works if the hg repos already exist at DROP_ROOT
::

@echo off
set REPO_ROOT=C:\Source\hg
set DROP_ROOT=C:\Documents and Settings\Tim\My Documents\My Dropbox\hg
set OLDDIR=%CD%

:: push ...
set REPO=envision
echo pushing repository [%REPO%] at %REPO_ROOT%\%REPO% to Dropbox
cd "%REPO_ROOT%\%REPO%"
hg push "%DROP_ROOT%\%REPO%"
:: ... and update
echo changing to directory %DROP_ROOT%\%REPO%
cd "%DROP_ROOT%\%REPO%"
hg up

echo.

:: push ...
set REPO=unified
echo pushing repository [%REPO%] at %REPO_ROOT%\%REPO% to Dropbox
cd "%REPO_ROOT%\%REPO%"
hg push "%DROP_ROOT%\%REPO%"
:: ... and update
echo changing to directory %DROP_ROOT%\%REPO%
cd "%DROP_ROOT%\%REPO%"
hg up

:: back where we started
cd %OLDDIR%

