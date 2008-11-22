:: Copy files from Mercurial repository to Dropbox
::

set REPOS=C:\Source\hg\unified\doc\thesis
set DROPBOX=C:\Documents and Settings\Tim\My Documents\My Dropbox\thesis
set CMP=cmp --silent

dir /a-d /s/b | grep -Ev "ATTIC|\.swp|~$|#$" > files.tmp

for /F "delims=" %%i in (files.tmp) do @echo %%i
:: need to get the root of the filename to make this work
::%CMP% %%i %DROPBOX%\

