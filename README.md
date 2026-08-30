# הורדות פתרונאי

ריפו זה מכיל אך ורק קובצי התקנה רשמיים וחתומים של מוצרי פתרונאי — לא קוד מקור.

## IVR Drive

כונן ענן לקווי ימות המשיח — הקבצים של הקו ישר בסייר של Windows.

**התקנה:** <https://ivr.pitronai.com/download/> — מורידים קובץ אחד ולוחצים עליו פעמיים.

| קובץ | תפקיד |
|---|---|
| `IVR-Drive-Setup.cmd` | המתקין. קובץ אחד, בלי תלויות |
| `IvrDrive-<גרסה>-x64.msix` | החבילה (עצמאית — כוללת ‎.NET ו-WindowsAppSDK) |
| `IvrDrive.appinstaller` | עדכון אוטומטי דרך App Installer |
| `ivr-drive-signing.cer` | תעודת החתימה, לפריסה ארגונית (GPO/Intune) |
| `SHA256SUMS.txt` | סיכומי בדיקה |

תגי השחרור: `ivr-drive-v<גרסה>`. דרישות: ‏Windows 10 גרסה 1809 ומעלה, ‏64-ביט, ‏NTFS.
