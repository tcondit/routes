set REPO="C:\Source\hg\unified"
set DROP="C:\Documents and Settings\Tim\My Documents\My Dropbox\unified"

cd %REPO%
echo Pushing updates to Mercurial repository at %REPO%
hg push %DROP%
echo done.
