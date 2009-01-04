set REPO="C:\Source\hg\unified"
set DROP="C:\Documents and Settings\Tim\My Documents\My Dropbox\unified"

echo Deleting %DROP% ...
rd /s/q %DROP%
echo done.

echo Cloning Mercurial repository at %REPO%
hg clone %REPO% %DROP%
echo done.
