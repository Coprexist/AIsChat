; AIsChat Launcher NSIS Installer Script
; =======================================
; Generates single .exe installer with:
; - Language selection at start
; - Custom installation directory
; - Desktop and Start Menu shortcuts
; - Uninstaller
; - Optional auto-start

!include "MUI2.nsh"

; --- Basic Information ---
Name "AIsChat Launcher"
OutFile "AIsChat-Installer.exe"
InstallDir "$LOCALAPPDATA\AIsChat"
InstallDirRegKey HKCU "Software\AIsChat" "InstallDir"
RequestExecutionLevel admin

; --- Version Info ---
VIProductVersion "0.3.14.0"
VIAddVersionKey "ProductName" "AIsChat Launcher"
VIAddVersionKey "CompanyName" "AIsChat"
VIAddVersionKey "FileVersion" "0.3.14"
VIAddVersionKey "FileDescription" "AIsChat Desktop Launcher Installer"

; --- Interface Settings ---
!define MUI_ICON "frontend\public\logo-transparent.ico"
!define MUI_UNICON "frontend\public\logo-transparent.ico"
!define MUI_ABORTWARNING

; --- Language Selection ---
; Show language selection dialog before welcome page
!define MUI_LANGDLL_ALLLANGUAGES

; --- Installation Pages ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; --- Uninstallation Pages ---
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; --- Languages ---
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; --- Language Dialog Settings ---
; Chinese texts
!define MUI_LANGDLL_WINDOWTITLE "选择安装语言"
!define MUI_LANGDLL_INFO "请选择安装过程中使用的语言："

!define MUI_WELCOMEPAGE_TITLE "欢迎安装 AIsChat 启动器"
!define MUI_WELCOMEPAGE_TEXT "本向导将引导您完成 AIsChat 启动器的安装。$\r$\n$\r$\nAIsChat 是一个本地 AI 社交网络，支持与多个 AI 角色进行对话。$\r$\n$\r$\n点击下一步继续。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\AIsChat.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 AIsChat"

; --- Installation Section ---
Section "AIsChat Launcher" SecMain
  SetOutPath "$INSTDIR"
  
  ; Copy all files
  File /r "dist\AIsChat\*.*"
  
  ; Write registry (install path)
  WriteRegStr HKCU "Software\AIsChat" "InstallDir" "$INSTDIR"
  
  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  
  ; Create Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\AIsChat"
  CreateShortCut "$SMPROGRAMS\AIsChat\AIsChat 启动器.lnk" "$INSTDIR\AIsChat.exe" "" "$INSTDIR\AIsChat.exe" 0
  CreateShortCut "$SMPROGRAMS\AIsChat\卸载 AIsChat.lnk" "$INSTDIR\Uninstall.exe"
  
  ; Create Desktop shortcut
  CreateShortCut "$DESKTOP\AIsChat 启动器.lnk" "$INSTDIR\AIsChat.exe" "" "$INSTDIR\AIsChat.exe" 0
  
  ; Write uninstall information to registry
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat" "DisplayName" "AIsChat 启动器"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat" "DisplayVersion" "0.3.14"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat" "Publisher" "AIsChat"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat" "NoRepair" 1
  
SectionEnd

; --- Uninstallation Section ---
Section "Uninstall"
  ; Delete files
  RMDir /r "$INSTDIR"
  
  ; Delete shortcuts
  Delete "$DESKTOP\AIsChat 启动器.lnk"
  RMDir /r "$SMPROGRAMS\AIsChat"
  
  ; Delete registry keys
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIsChat"
  DeleteRegKey HKCU "Software\AIsChat"
  
SectionEnd

; --- Language Selection Function ---
Function .onInit
  ; Show language selection dialog
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd
