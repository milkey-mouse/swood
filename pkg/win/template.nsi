!define PRODUCT_NAME "[[ib.appname]]"
!define PRODUCT_VERSION "[[ib.version]]"
!define PY_VERSION "[[ib.py_version]]"
!define PY_MAJOR_VERSION "[[ib.py_major_version]]"
!define BITNESS "[[ib.py_bitness]]"
!define ARCH_TAG "[[arch_tag]]"
!define INSTALLER_NAME "[[ib.installer_name]]"
!define PRODUCT_ICON "[[icon]]"

Unicode true

RequestExecutionLevel user

SetCompressor lzma

[% block modernui %]
; Modern UI installer stuff 
!include "MUI2.nsh"
!include "FileFunc.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "${PRODUCT_ICON}"

; UI pages
[% block ui_pages %]
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
;!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
[% endblock ui_pages %]
!insertmacro MUI_LANGUAGE "English"
[% endblock modernui %]

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "${INSTALLER_NAME}"
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"
ShowInstDetails show

Section -SETTINGS
  SetOutPath "$INSTDIR"
  SetOverwrite ifnewer
SectionEnd

[% block sections %]

Section "!${PRODUCT_NAME}" sec_app
  SectionIn RO
  SetShellVarContext all
  File ${PRODUCT_ICON}
  SetOutPath "$INSTDIR\pkgs"
  File /r "pkgs\*.*"
  SetOutPath "$INSTDIR"
  
  ; Install files
  [% for destination, group in grouped_files %]
    SetOutPath "[[destination]]"
    [% for file in group %]
      File "[[ file ]]"
    [% endfor %]
  [% endfor %]
  
  ; Install directories
  [% for dir, destination in ib.install_dirs %]
    SetOutPath "[[ pjoin(destination, dir) ]]"
    File /r "[[dir]]\*.*"
  [% endfor %]

  [% block install_commands %]
  [% if has_commands %]
    nsExec::ExecToLog '[[ python ]] -Es "$INSTDIR\_rewrite_shebangs.py" "$INSTDIR\bin"'
    nsExec::ExecToLog '[[ python ]] -Es "$INSTDIR\pkgs\_user_path.py" add "$INSTDIR\bin"'
  [% endif %]
  [% endblock install_commands %]
  
  ; Byte-compile Python files.
  DetailPrint "Byte-compiling Python modules..."
  nsExec::ExecToLog '[[ python ]] -m compileall -q "$INSTDIR\pkgs"'
  WriteUninstaller $INSTDIR\uninstall.exe
  ; Add ourselves to Add/remove programs
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "Publisher" "Milkey Mouse"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "InstallSource" "https://github.com/milkey-mouse/swood"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "Readme" "https://github.com/milkey-mouse/swood/blob/master/README.md"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "HelpLink" "https://github.com/milkey-mouse/swood/wiki"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "URLInfoAbout" "https://github.com/milkey-mouse/swood/blob/master/README.md"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "DisplayVersion" "[[ib.version]]"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "QuietUninstallString" "$\"$INSTDIR\uninstall.exe$\" /S"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "DisplayIcon" "$INSTDIR\${PRODUCT_ICON}"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
                   "NoRepair" 1

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" "EstimatedSize" "$0"

  ; Check if we need to reboot
  IfRebootFlag 0 noreboot
    MessageBox MB_YESNO "A reboot is required to finish the installation. Do you wish to reboot now?" \
                /SD IDNO IDNO noreboot
      Reboot
  noreboot:
SectionEnd

Section "Uninstall"
  SetShellVarContext all
  Delete $INSTDIR\uninstall.exe
  Delete "$INSTDIR\${PRODUCT_ICON}"

  ; Remove ourselves from %PATH%
  [% block uninstall_commands %]
  [% if has_commands %]
    nsExec::ExecToLog '[[ python ]] -Es "$INSTDIR\pkgs\_user_path.py" remove "$INSTDIR\bin"'
  [% endif %]
  [% endblock uninstall_commands %]

  RMDir /r "$INSTDIR\pkgs"

  ; Uninstall files
  [% for file, destination in ib.install_files %]
    Delete "[[pjoin(destination, file)]]"
  [% endfor %]
  Delete "$INSTDIR\ffmpeg.exe"
  Delete "$INSTDIR\ffprobe.exe"
  ; Uninstall directories
  [% for dir, destination in ib.install_dirs %]
    RMDir /r "[[pjoin(destination, dir)]]"
  [% endfor %]
  RMDir $INSTDIR
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
SectionEnd

[% endblock sections %]

; Functions

Function .onMouseOverSection
    ; Find which section the mouse is over, and set the corresponding description.
    FindWindow $R0 "#32770" "" $HWNDPARENT
    GetDlgItem $R0 $R0 1043 ; description item (must be added to the UI)

    [% block mouseover_messages %]
    StrCmp $0 ${sec_app} "" +2
      SendMessage $R0 ${WM_SETTEXT} 0 "STR:${PRODUCT_NAME}"
    
    [% endblock mouseover_messages %]
FunctionEnd