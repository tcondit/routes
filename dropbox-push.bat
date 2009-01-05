::
:: Some of the folders in REPO_ROOT are Mercurial repositories, some of them
:: are not.
::

set REPO_ROOT="C:\Source\hg\unified"
set DROP_ROOT="C:\Documents and Settings\Tim\My Documents\My Dropbox\hg"
set CP="cp -priv --reply=yes"

set REPO="envision"
echo Pushing updates to Mercurial repository at %REPO_ROOT%\%REPO%
cd %REPO_ROOT%\%REPO%
hg push %DROP%
echo done.

set REPO="unified"
echo Pushing updates to Mercurial repository at %REPO_ROOT%\%REPO%
cd %REPO_ROOT%\%REPO%
hg push %DROP%
echo done.

::
:: This is rude and crude.
::
%CP% %REPO_ROOT%\django %DROP_ROOT%
%CP% %REPO_ROOT%\tags %DROP_ROOT%
%CP% %REPO_ROOT%\zipfiles %DROP_ROOT%
