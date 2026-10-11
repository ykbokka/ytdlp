import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    width: 1220
    height: 820
    minimumWidth: 930
    minimumHeight: 650
    visible: true
    title: "YouTube Toolkit"
    color: bgColor

    property bool darkMode: true
    property bool introComplete: false
    property int currentPage: 0
    property string statusMessage: "Starting Qt Quick backend…"
    property string logText: ""
    property real downloadPercent: 0
    property string progressText: "Ready"
    property bool isPaused: false
    property string metadataThumbnail: ""
    property var previewData: ({})
    property var metadataValues: ({title:"", artist:"", album:"", date:"", genre:"", comment:"", path:""})
    property var queueItems: []
    property var libraryRows: []
    property string libraryFolder: ""
    property bool rewriteTitles: false
    property string downloadDirectory: ""
    property string metadataFolderPath: ""
    property string coverFolderPath: ""
    property string coverMediaPathValue: ""
    property string coverSourcePath: ""
    property string cropSourcePath: ""
    property string cropPositionValue: "Center"
    property string cookiePath: ""
    property bool hasCookies: false
    property string performanceMode: "aggressive"
    property string conflictMode: "rename"
    property string downloadUrl: ""
    property string fileType: "Video (MKV)"
    property string quality: "Best available"
    property string audioFormat: "FLAC"
    property string subtitleMode: "No subtitles"
    property var qualityOptions: ["Best available", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
    property color bgColor: darkMode ? "#0B0D12" : "#F2F4F8"
    property color panelColor: darkMode ? "#151821" : "#FFFFFF"
    property color elevatedColor: darkMode ? "#1C2230" : "#F7F8FC"
    property color inputColor: darkMode ? "#0F121A" : "#F1F3F8"
    property color borderColor: darkMode ? "#292F3D" : "#E0E4ED"
    property color textColor: darkMode ? "#F4F6FB" : "#202535"
    property color mutedColor: darkMode ? "#929BAD" : "#737D90"
    property color accentColor: darkMode ? "#76A7FF" : "#2868E8"
    property color accentSoftColor: darkMode ? "#233657" : "#E5EEFF"
    property color hoverColor: darkMode ? "#222A3A" : "#EDF1F8"
    property color successColor: darkMode ? "#52D6A0" : "#218653"

    Behavior on textColor { ColorAnimation { duration: 240
easing.type: Easing.OutCubic } }
    Behavior on mutedColor { ColorAnimation { duration: 240
easing.type: Easing.OutCubic } }
    Behavior on accentColor { ColorAnimation { duration: 240
easing.type: Easing.OutCubic } }
    Behavior on successColor { ColorAnimation { duration: 240
easing.type: Easing.OutCubic } }
    property var navItems: [
        {title:"Downloader", icon:"↓"},
        {title:"Queue", icon:"≡"},
        {title:"Metadata", icon:"✎"},
        {title:"Cover Art", icon:"▧"},
        {title:"Crop Art", icon:"□"},
        {title:"Library Overhaul", icon:"♫"},
        {title:"Settings", icon:"⚙"},
        {title:"Activity", icon:"◷"}
    ]
    property var pageComponents: [downloaderPage, queuePage, metadataPage, coverPage, cropPage, libraryPage, settingsPage, activityPage]

    function appendLog(line) {
        logText = (logText + line + "\n").split("\n").slice(-220).join("\n")
    }
    function updatePage() {
        if (!introComplete) return
        pageLoader.opacity = 0
        pageLoader.y = 15
        pageLoader.scale = 0.992
        pageAnimation.restart()
    }
    function applySettings(s) {
        if (!s) return
        downloadDirectory = s.downloadDir || ""
        metadataFolderPath = s.metadataDir || ""
        coverFolderPath = s.coverDir || ""
        libraryFolder = s.pipelineDir || ""
        cookiePath = s.cookiePath || ""
        hasCookies = !!s.hasCookies
        performanceMode = s.performanceMode || "aggressive"
        conflictMode = s.conflictMode || "rename"
        fileType = s.fileType || "Video (MKV)"
        quality = s.quality || "Best available"
        audioFormat = s.audioFormat || "FLAC"
        subtitleMode = s.subtitleMode || "No subtitles"
        darkMode = (s.appearanceMode || "dark") !== "light"
    }
    function startDownload() {
        downloadPercent = 0
        progressText = "Starting…"
        backend.startDownload(downloadUrl, fileType, quality, audioFormat, subtitleMode)
    }
    function runQueue() {
        backend.startQueue(fileType, quality, audioFormat, subtitleMode)
    }
    function persistDownloadOptions() {
        backend.setDownloadOptions(fileType, quality, audioFormat, subtitleMode)
    }

    background: Rectangle {
        color: root.bgColor
        Behavior on color { ColorAnimation { duration: 260
easing.type: Easing.OutCubic } }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 21
        spacing: 14

        Rectangle {
            id: header
            Layout.fillWidth: true
            Layout.preferredHeight: 82
            radius: 21
            color: root.panelColor
            border.width: 1
            border.color: root.borderColor
            opacity: 0
            y: -9
            Behavior on color { ColorAnimation { duration: 260
easing.type: Easing.OutCubic } }
            Behavior on border.color { ColorAnimation { duration: 260 } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 17
                spacing: 12
                Rectangle {
                    Layout.preferredWidth: 48
                    Layout.preferredHeight: 48
                    radius: 15
                    color: root.accentSoftColor
                    border.width: 1
                    border.color: root.borderColor
                    Behavior on color { ColorAnimation { duration: 260 } }
                    Text {
                        anchors.centerIn: parent
                        text: "♫"
                        color: root.accentColor
                        font.pixelSize: 25
                        font.bold: true
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text { text: "YouTube Toolkit"
color: root.textColor
font.pixelSize: 21
font.bold: true }
                    Text { text: "Downloads, metadata, artwork & library tools"
color: root.mutedColor
font.pixelSize: 11 }
                }
                Rectangle {
                    Layout.preferredWidth: 100
                    Layout.preferredHeight: 29
                    radius: 14
                    color: root.darkMode ? "#142B26" : "#E4F6EC"
                    border.width: 1
                    border.color: root.darkMode ? "#285345" : "#C4E8D2"
                    Behavior on color { ColorAnimation { duration: 260 } }
                    Row {
                        anchors.centerIn: parent
                        spacing: 7
                        Rectangle { width: 6
height: 6
radius: 3
anchors.verticalCenter: parent.verticalCenter
color: root.successColor }
                        Text { text: "QT QUICK"
color: root.successColor
font.pixelSize: 9
font.bold: true
anchors.verticalCenter: parent.verticalCenter }
                    }
                }
                Button {
                    id: themeButton
                    Layout.preferredWidth: 41
                    Layout.preferredHeight: 41
                    text: root.darkMode ? "☼" : "☾"
                    onClicked: {
                        root.darkMode = !root.darkMode
                        backend.setAppearanceMode(root.darkMode ? "dark" : "light")
                    }
                    background: Rectangle {
                        radius: 13
                        color: themeButton.down ? root.accentSoftColor : themeButton.hovered ? root.hoverColor : root.elevatedColor
                        border.width: 1
                        border.color: root.borderColor
                        Behavior on color { ColorAnimation { duration: 180 } }
                    }
                    contentItem: Text { text: themeButton.text
color: root.textColor
font.pixelSize: 20
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                    scale: down ? 0.94 : 1
                    Behavior on scale { NumberAnimation { duration: 110
easing.type: Easing.OutCubic } }
                    ToolTip.visible: hovered
                    ToolTip.text: "Toggle appearance"
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            Rectangle {
                id: sidebar
                Layout.preferredWidth: 205
                Layout.minimumWidth: 175
                Layout.fillHeight: true
                radius: 21
                color: root.panelColor
                border.width: 1
                border.color: root.borderColor
                Behavior on color { ColorAnimation { duration: 260 } }
                Behavior on border.color { ColorAnimation { duration: 260 } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 15
                    anchors.bottomMargin: 13
                    spacing: 6
                    Text {
                        text: "WORKSPACE"
                        color: root.mutedColor
                        font.pixelSize: 9
                        font.bold: true
                        font.letterSpacing: 1.5
                        Layout.leftMargin: 10
                        Layout.bottomMargin: 5
                    }
                    Repeater {
                        model: root.navItems
                        delegate: Item {
                            id: navItem
                            required property int index
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42
                            Rectangle {
                                anchors.fill: parent
                                radius: 12
                                color: root.currentPage === navItem.index ? root.accentSoftColor : navMouse.containsMouse ? root.hoverColor : "transparent"
                                Behavior on color { ColorAnimation { duration: 170
easing.type: Easing.OutCubic } }
                            }
                            Rectangle {
                                width: 3
                                height: 19
                                radius: 2
                                anchors.left: parent.left
                                anchors.leftMargin: 1
                                anchors.verticalCenter: parent.verticalCenter
                                color: root.accentColor
                                opacity: root.currentPage === navItem.index ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 160 } }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 7
                                spacing: 9
                                Text {
                                    text: navItem.modelData.icon
                                    color: root.currentPage === navItem.index ? root.accentColor : root.mutedColor
                                    font.pixelSize: 17
                                    Layout.preferredWidth: 20
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                Text {
                                    text: navItem.modelData.title
                                    color: root.currentPage === navItem.index ? root.textColor : root.mutedColor
                                    font.pixelSize: 11
                                    font.bold: root.currentPage === navItem.index
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }
                            MouseArea {
                                id: navMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.currentPage = navItem.index
                            }
                            scale: navMouse.pressed ? 0.98 : 1
                            Behavior on scale { NumberAnimation { duration: 100
easing.type: Easing.OutCubic } }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 82
                        radius: 15
                        color: root.elevatedColor
                        border.width: 1
                        border.color: root.borderColor
                        Behavior on color { ColorAnimation { duration: 260 } }
                        Column {
                            anchors.fill: parent
                            anchors.margins: 11
                            spacing: 5
                            Text { text: "BACKEND"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                            Text { text: "Python · yt-dlp"
color: root.textColor
font.pixelSize: 11
font.bold: true }
                            Text { text: "Async operations"
color: root.successColor
font.pixelSize: 10 }
                        }
                    }
                }
            }

            Rectangle {
                id: contentPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 21
                color: root.panelColor
                border.width: 1
                border.color: root.borderColor
                clip: true
                Behavior on color { ColorAnimation { duration: 260
easing.type: Easing.OutCubic } }
                Behavior on border.color { ColorAnimation { duration: 260 } }

                Loader {
                    id: pageLoader
                    anchors.fill: parent
                    anchors.margins: 21
                    sourceComponent: root.pageComponents[root.currentPage]
                    opacity: 1
                    y: 0
                    scale: 1
                }
                ParallelAnimation {
                    id: pageAnimation
                    NumberAnimation { target: pageLoader
property: "opacity"
from: 0
to: 1
duration: 260
easing.type: Easing.OutCubic }
                    NumberAnimation { target: pageLoader
property: "y"
from: 15
to: 0
duration: 320
easing.type: Easing.OutCubic }
                    NumberAnimation { target: pageLoader
property: "scale"
from: 0.992
to: 1
duration: 320
easing.type: Easing.OutCubic }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 22
            spacing: 8
            Rectangle { width: 6
height: 6
radius: 3
color: root.downloadPercent > 0 && root.downloadPercent < 100 ? root.accentColor : root.successColor
Layout.alignment: Qt.AlignVCenter }
            Text { Layout.fillWidth: true
text: root.statusMessage
color: root.mutedColor
font.pixelSize: 10
elide: Text.ElideRight
verticalAlignment: Text.AlignVCenter }
            Text { text: root.downloadPercent > 0 ? Math.round(root.downloadPercent) + "%" : "READY"
color: root.accentColor
font.pixelSize: 9
font.bold: true }
        }
    }

    MessageDialog {
        id: confirmFullOverhaulDialog
        title: "Run full FLAC overhaul?"
        text: "This operation changes metadata and artwork in the selected FLAC library."
        informativeText: "YouTube Music matches will replace ARTIST, ALBUM and DATE, update matched cover art when available, and crop covers to square. A backup of your current files is recommended."
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: backend.runFullOverhaul(root.libraryFolder)
    }

    FileDialog {
        id: metadataFileDialog
        title: "Choose tagged media file"
        nameFilters: ["Supported tagged media (*.flac *.mp3 *.m4a *.mp4 *.m4v *.mov *.opus *.ogg *.wav *.aac *.wma)", "All files (*)"]
        onAccepted: backend.inspectMediaFile(selectedFile.toLocalFile())
    }
    FileDialog {
        id: coverMediaDialog
        title: "Choose media file to update"
        nameFilters: ["Supported media (*.flac *.mp3 *.m4a *.mp4 *.m4v *.mov *.mkv *.opus *.ogg *.wav *.aac *.wma)", "All files (*)"]
        onAccepted: root.coverMediaPathValue = selectedFile.toLocalFile()
    }
    FileDialog {
        id: coverImageDialog
        title: "Choose cover image"
        nameFilters: ["Images (*.jpg *.jpeg *.png *.webp)", "All files (*)"]
        onAccepted: root.coverSourcePath = selectedFile.toLocalFile()
    }
    FileDialog {
        id: cropImageDialog
        title: "Choose source artwork"
        nameFilters: ["Images (*.jpg *.jpeg *.png *.webp *.bmp)", "All files (*)"]
        onAccepted: root.cropSourcePath = selectedFile.toLocalFile()
    }
    FileDialog {
        id: cropSaveDialog
        title: "Save square artwork"
        fileMode: FileDialog.SaveFile
        nameFilters: ["JPEG image (*.jpg)", "All files (*)"]
        onAccepted: backend.cropArtwork(root.cropSourcePath, selectedFile.toLocalFile(), root.cropPositionValue)
    }
    FileDialog {
        id: cookieFileDialog
        title: "Choose Netscape cookies.txt"
        nameFilters: ["Cookie files (*.txt)", "All files (*)"]
        onAccepted: backend.setCookieFile(selectedFile.toLocalFile())
    }
    FolderDialog {
        id: outputFolderDialog
        title: "Choose download folder"
        onAccepted: backend.setDownloadDirectory(selectedFolder.toLocalFile())
    }
    FolderDialog {
        id: libraryFolderDialog
        title: "Choose media library folder"
        onAccepted: {
            root.libraryFolder = selectedFolder.toLocalFile()
            backend.setOperationDirectory("pipeline", root.libraryFolder)
            backend.scanLibrary(root.libraryFolder)
        }
    }
    FolderDialog {
        id: metadataFolderDialog
        title: "Choose FLAC metadata folder"
        onAccepted: {
            root.metadataFolderPath = selectedFolder.toLocalFile()
            backend.setOperationDirectory("metadata", root.metadataFolderPath)
        }
    }
    FolderDialog {
        id: coverFolderDialog
        title: "Choose FLAC cover-art folder"
        onAccepted: {
            root.coverFolderPath = selectedFolder.toLocalFile()
            backend.setOperationDirectory("cover", root.coverFolderPath)
        }
    }

    Connections {
        target: backend
        function onStatusChanged(message) { root.statusMessage = message }
        function onLogMessage(message) { root.appendLog(message) }
        function onProgressChanged(percent, detail) {
            root.downloadPercent = percent
            root.progressText = detail
        }
        function onPreviewReady(data) {
            root.previewData = data
            var choices = ["Best available"]
            if (data.heights) {
                for (var i = 0; i < data.heights.length; ++i)
                    choices.push(String(data.heights[i]) + "p")
            }
            var previousQuality = root.quality
            if (previousQuality && previousQuality !== "Best available" && choices.indexOf(previousQuality) < 0)
                choices.push(previousQuality)
            root.qualityOptions = choices
            if (choices.indexOf(root.quality) < 0)
                root.quality = choices[0]
            root.persistDownloadOptions()
            root.statusMessage = "Source preview ready: " + (data.title || "")
        }
        function onQueueChanged(items) { root.queueItems = items }
        function onOperationFinished(id, ok, message) {
            var isDownloadOperation = id.indexOf("download-") === 0 || id.indexOf("queue-run-") === 0
            root.appendLog((ok ? "SUCCESS: " : "FAILED: ") + message)
            if (isDownloadOperation) {
                root.isPaused = false
                if (ok)
                    root.downloadPercent = 100
            }
        }
        function onMetadataLoaded(data) { root.metadataValues = data
if (data.thumbnail) root.metadataThumbnail = data.thumbnail }
        function onLibraryScanReady(data) {
            root.libraryFolder = data.folder || root.libraryFolder
            root.libraryRows = data.rows || []
            root.statusMessage = "Library scan complete: " + root.libraryRows.length + " file(s)."
        }
        function onSettingsChanged(settings) { root.applySettings(settings) }
    }

    Component.onCompleted: {
        root.applySettings(backend.getSettings())
        introAnimation.start()
    }
    onCurrentPageChanged: updatePage()

    ParallelAnimation {
        id: introAnimation
        NumberAnimation { target: header
property: "opacity"
from: 0
to: 1
duration: 400
easing.type: Easing.OutCubic }
        NumberAnimation { target: header
property: "y"
from: -9
to: 0
duration: 430
easing.type: Easing.OutCubic }
        onFinished: root.introComplete = true
    }

    Component {
        id: downloaderPage
        Flickable {
            id: downloaderFlick
            contentWidth: width
            contentHeight: downloaderContent.implicitHeight
            clip: true
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: downloaderContent
                width: downloaderFlick.width
                spacing: 13
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text { text: "Downloader"
color: root.textColor
font.pixelSize: 24
font.bold: true }
                    Text { text: "Preview a source, choose the output, and download in the background."
color: root.mutedColor
font.pixelSize: 11 }
                }
                Rectangle {
                    Layout.fillWidth: true
                    radius: 17
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    implicitHeight: sourceColumn.implicitHeight + 30
                    Behavior on color { ColorAnimation { duration: 230 } }
                    ColumnLayout {
                        id: sourceColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 15
                        spacing: 10
                        Text { text: "SOURCE URL"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            TextField {
                                id: urlField
                                Layout.fillWidth: true
                                Layout.preferredHeight: 43
                                text: root.downloadUrl
                                placeholderText: "Paste a YouTube or YouTube Music URL…"
                                color: root.textColor
                                placeholderTextColor: root.mutedColor
                                selectByMouse: true
                                font.pixelSize: 11
                                onTextEdited: root.downloadUrl = text
                                background: Rectangle {
                                    radius: 12
                                    color: root.inputColor
                                    border.width: urlField.activeFocus ? 1.5 : 1
                                    border.color: urlField.activeFocus ? root.accentColor : root.borderColor
                                    Behavior on border.color { ColorAnimation { duration: 150 } }
                                }
                            }
                            Button {
                                id: previewButton
                                text: "Preview"
                                onClicked: { root.downloadUrl = urlField.text
backend.preview(urlField.text) }
                                background: Rectangle { radius: 12
color: previewButton.down ? "#2859B9" : previewButton.hovered ? "#4C83F3" : "#3475EE"
Behavior on color { ColorAnimation { duration: 120 } } }
                                contentItem: Text { text: previewButton.text
color: "white"
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                            }
                            Button {
                                id: addQueueButton
                                text: "Add to Queue"
                                onClicked: { root.downloadUrl = urlField.text
backend.addQueueUrl(urlField.text, root.fileType, root.quality, root.audioFormat, root.subtitleMode) }
                                background: Rectangle { radius: 12
color: addQueueButton.hovered ? root.hoverColor : root.panelColor
border.width: 1
border.color: root.borderColor
Behavior on color { ColorAnimation { duration: 120 } } }
                                contentItem: Text { text: addQueueButton.text
color: root.textColor
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Text { text: "FILE TYPE"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        ComboBox {
                            id: fileTypeBox
                            Layout.fillWidth: true
                            model: ["Video (MKV)", "Video (MP4)", "Audio only"]
                            currentIndex: Math.max(0, model.indexOf(root.fileType))
                            onActivated: {
root.fileType = currentText
root.persistDownloadOptions()
}
                            contentItem: Text { leftPadding: 12
rightPadding: 28
text: fileTypeBox.displayText
color: root.textColor
font.pixelSize: 11
verticalAlignment: Text.AlignVCenter
elide: Text.ElideRight }
                            background: Rectangle { radius: 11
color: root.inputColor
border.width: 1
border.color: root.borderColor }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Text { text: "QUALITY CEILING"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        ComboBox {
                            id: qualityBox
                            Layout.fillWidth: true
                            enabled: fileTypeBox.currentText !== "Audio only"
                            opacity: enabled ? 1 : 0.55
                            model: root.qualityOptions
                            currentIndex: Math.max(0, root.qualityOptions.indexOf(root.quality))
                            onActivated: {
root.quality = currentText
root.persistDownloadOptions()
}
                            contentItem: Text { leftPadding: 12
rightPadding: 28
text: qualityBox.displayText
color: root.textColor
font.pixelSize: 11
verticalAlignment: Text.AlignVCenter
elide: Text.ElideRight }
                            background: Rectangle { radius: 11
color: root.inputColor
border.width: 1
border.color: root.borderColor }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Text { text: "AUDIO FORMAT"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        ComboBox {
                            id: audioFormatBox
                            Layout.fillWidth: true
                            model: ["FLAC", "MP3", "M4A", "Opus"]
                            currentIndex: Math.max(0, model.indexOf(root.audioFormat))
                            enabled: fileTypeBox.currentText === "Audio only"
                            opacity: enabled ? 1 : 0.55
                            onActivated: {
root.audioFormat = currentText
root.persistDownloadOptions()
}
                            contentItem: Text { leftPadding: 12
rightPadding: 28
text: audioFormatBox.displayText
color: root.textColor
font.pixelSize: 11
verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { radius: 11
color: root.inputColor
border.width: 1
border.color: root.borderColor }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Text { text: "SUBTITLES"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        ComboBox {
                            id: subtitleBox
                            Layout.fillWidth: true
                            model: ["No subtitles", "Auto subtitles", "Manual subtitles"]
                            currentIndex: Math.max(0, model.indexOf(root.subtitleMode))
                            onActivated: {
root.subtitleMode = currentText
root.persistDownloadOptions()
}
                            contentItem: Text { leftPadding: 12
rightPadding: 28
text: subtitleBox.displayText
color: root.textColor
font.pixelSize: 11
verticalAlignment: Text.AlignVCenter
elide: Text.ElideRight }
                            background: Rectangle { radius: 11
color: root.inputColor
border.width: 1
border.color: root.borderColor }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    radius: 16
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    implicitHeight: previewRow.implicitHeight + 24
                    Behavior on color { ColorAnimation { duration: 230 } }
                    RowLayout {
                        id: previewRow
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 12
                        Rectangle {
                            Layout.preferredWidth: 116
                            Layout.preferredHeight: 66
                            radius: 10
                            color: root.inputColor
                            clip: true
                            Image { anchors.fill: parent
source: root.previewData.thumbnail || ""
fillMode: Image.PreserveAspectCrop
asynchronous: true
cache: true }
                            Text { anchors.centerIn: parent
visible: !root.previewData.thumbnail
text: "♫"
color: root.mutedColor
font.pixelSize: 22 }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text { text: root.previewData.title || "No source preview yet"
color: root.textColor
font.pixelSize: 13
font.bold: true
elide: Text.ElideRight
Layout.fillWidth: true }
                            Text { text: (root.previewData.uploader || "—") + "   •   " + (root.previewData.duration || "—")
color: root.mutedColor
font.pixelSize: 10
elide: Text.ElideRight
Layout.fillWidth: true }
                            Text { text: root.previewData.heights ? root.previewData.heights.join("p  ·  ") + "p available" : "Choose Preview to inspect available formats"
color: root.accentColor
font.pixelSize: 10
elide: Text.ElideRight
Layout.fillWidth: true }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    radius: 14
                    color: root.inputColor
                    border.width: 1
                    border.color: root.borderColor
                    implicitHeight: progressColumn.implicitHeight + 20
                    ColumnLayout {
                        id: progressColumn
                        anchors.fill: parent
                        anchors.margins: 11
                        spacing: 7
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: "DOWNLOAD PROGRESS"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 0.8 }
                            Item { Layout.fillWidth: true }
                            Text { text: root.progressText
color: root.accentColor
font.pixelSize: 10
elide: Text.ElideRight
Layout.maximumWidth: 230 }
                        }
                        ProgressBar {
                            Layout.fillWidth: true
                            from: 0
                            to: 100
                            value: root.downloadPercent
                            background: Rectangle { implicitHeight: 7
radius: 4
color: root.borderColor }
                            contentItem: Item {
                                implicitHeight: 7
                                Rectangle { width: parent.width * Math.max(0, Math.min(1, root.downloadPercent / 100))
height: parent.height
radius: 4
color: root.accentColor
Behavior on width { NumberAnimation { duration: 100
easing.type: Easing.OutCubic } } }
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 9
                    Button {
                        id: downloadButton
                        text: (urlField.text.indexOf("list=") >= 0 || urlField.text.indexOf("/playlist") >= 0) ? "Add Playlist to Queue" : "Start Download  →"
                        Layout.preferredHeight: 43
                        Layout.preferredWidth: 190
                        onClicked: {
                            root.downloadUrl = urlField.text
                            if (urlField.text.indexOf("list=") >= 0 || urlField.text.indexOf("/playlist") >= 0)
                                backend.addQueueUrl(urlField.text)
                            else
                                root.startDownload()
                        }
                        background: Rectangle { radius: 12
color: downloadButton.down ? "#2859B9" : downloadButton.hovered ? "#4C83F3" : "#3475EE"
Behavior on color { ColorAnimation { duration: 130 } } }
                        contentItem: Text { text: downloadButton.text
color: "white"
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                        scale: down ? 0.98 : 1
                        Behavior on scale { NumberAnimation { duration: 100
easing.type: Easing.OutCubic } }
                    }
                    Button {
                        id: pauseButton
                        text: root.isPaused ? "Resume" : "Pause"
                        Layout.preferredHeight: 43
                        onClicked: root.isPaused = backend.togglePause()
                        background: Rectangle { radius: 12
color: pauseButton.hovered ? root.hoverColor : root.elevatedColor
border.width: 1
border.color: root.borderColor }
                        contentItem: Text { text: pauseButton.text
color: root.textColor
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                    }
                    Button {
                        id: stopButton
                        text: "Stop"
                        Layout.preferredHeight: 43
                        onClicked: { root.isPaused = false
backend.stopDownload() }
                        background: Rectangle { radius: 12
color: stopButton.hovered ? (root.darkMode ? "#42242A" : "#FBE7E8") : root.elevatedColor
border.width: 1
border.color: root.borderColor }
                        contentItem: Text { text: stopButton.text
color: root.darkMode ? "#FF8D99" : "#B42332"
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                    }
                    Item { Layout.fillWidth: true }
                    Text { text: root.downloadDirectory ? "Save to: " + root.downloadDirectory : "Set the download folder in Settings"
color: root.mutedColor
font.pixelSize: 9
elide: Text.ElideMiddle
Layout.maximumWidth: 270 }
                }
            }
        }
    }

    Component {
        id: queuePage
        ColumnLayout {
            spacing: 12
            Text { text: "Download Queue"
color: root.textColor
font.pixelSize: 24
font.bold: true }
            Text { text: "Add a single URL or expand a playlist, then process items sequentially."
color: root.mutedColor
font.pixelSize: 11 }
            RowLayout {
                Layout.fillWidth: true
                Button { text: "Start Pending"
onClicked: { root.downloadPercent = 0
backend.startQueue(root.fileType, root.quality, root.audioFormat, root.subtitleMode) }
background: Rectangle { radius: 11
color: "#3475EE" }
contentItem: Text { text: parent.text
color: "white"
font.bold: true
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                Button { text: root.isPaused ? "Resume" : "Pause"
onClicked: root.isPaused = backend.togglePause()
background: Rectangle { radius: 11
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                Button { text: "Stop"
onClicked: { root.isPaused = false
backend.stopDownload() }
background: Rectangle { radius: 11
color: root.darkMode ? "#42242A" : "#FBE7E8"
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.darkMode ? "#FF8D99" : "#B42332"
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                Button { text: "Clear Queue"
onClicked: backend.clearQueue()
background: Rectangle { radius: 11
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                Item { Layout.fillWidth: true }
                Text { text: root.queueItems.length + " item(s)"
color: root.mutedColor
font.pixelSize: 10 }
            }
            ListView {
                id: queueList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 7
                model: root.queueItems
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property var modelData
                    width: queueList.width
                    height: 64
                    radius: 13
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 11
                        spacing: 10
                        Rectangle { Layout.preferredWidth: 34
Layout.preferredHeight: 34
radius: 11
color: root.accentSoftColor
Text { anchors.centerIn: parent
text: "♫"
color: root.accentColor
font.pixelSize: 17 } }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: modelData.title || modelData.url
color: root.textColor
font.pixelSize: 11
font.bold: true
elide: Text.ElideRight
Layout.fillWidth: true }
                            Text { text: (modelData.status || "Pending") + "  •  " + (modelData.duration || "—")
color: modelData.status === "Failed" ? "#FF7B86" : root.mutedColor
font.pixelSize: 10 }
                        }
                        Button {
                            text: "Remove"
                            onClicked: backend.removeQueueItem(modelData.id)
                            background: Rectangle { radius: 9
color: parent.hovered ? root.hoverColor : "transparent" }
                            contentItem: Text { text: parent.text
color: root.mutedColor
font.pixelSize: 10
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                        }
                    }
                }
                Rectangle {
                    anchors.centerIn: parent
                    visible: root.queueItems.length === 0
                    width: Math.min(parent.width - 40, 350)
                    height: 110
                    radius: 16
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    Column {
                        anchors.centerIn: parent
                        spacing: 8
                        Text { anchors.horizontalCenter: parent.horizontalCenter
text: "≡"
color: root.accentColor
font.pixelSize: 27 }
                        Text { anchors.horizontalCenter: parent.horizontalCenter
text: "Your queue is empty"
color: root.textColor
font.pixelSize: 14
font.bold: true }
                        Text { anchors.horizontalCenter: parent.horizontalCenter
text: "Use Add to Queue on the Downloader page."
color: root.mutedColor
font.pixelSize: 10 }
                    }
                }
            }
        }
    }

    Component {
        id: metadataPage
        Flickable {
            contentWidth: width
            contentHeight: metadataContent.implicitHeight
            clip: true
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: metadataContent
                width: parent.width
                spacing: 12
                Text { text: "Metadata Editor"
color: root.textColor
font.pixelSize: 24
font.bold: true }
                Text { text: "Read and update common tags on supported audio files."
color: root.mutedColor
font.pixelSize: 11 }
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: metadataPath
Layout.fillWidth: true
placeholderText: "Choose a media file…"
text: root.metadataValues.path || ""
color: root.textColor
placeholderTextColor: root.mutedColor
selectByMouse: true
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                    Button { text: "Browse"
onClicked: metadataFileDialog.open()
background: Rectangle { radius: 10
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 10
                    Text { text: "Title"
color: root.mutedColor
font.pixelSize: 10 }
                    Text { text: "Artist"
color: root.mutedColor
font.pixelSize: 10 }
                    TextField { id: metaTitle
Layout.fillWidth: true
text: root.metadataValues.title || ""
placeholderText: "Title"
color: root.textColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
onTextEdited: root.metadataValues.title = text }
                    TextField { id: metaArtist
Layout.fillWidth: true
text: root.metadataValues.artist || ""
placeholderText: "Artist"
color: root.textColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
onTextEdited: root.metadataValues.artist = text }
                    Text { text: "Album"
color: root.mutedColor
font.pixelSize: 10 }
                    Text { text: "Year / Date"
color: root.mutedColor
font.pixelSize: 10 }
                    TextField { id: metaAlbum
Layout.fillWidth: true
text: root.metadataValues.album || ""
placeholderText: "Album"
color: root.textColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
onTextEdited: root.metadataValues.album = text }
                    TextField { id: metaDate
Layout.fillWidth: true
text: root.metadataValues.date || ""
placeholderText: "2025"
color: root.textColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
onTextEdited: root.metadataValues.date = text }
                    Text { text: "Genre"
color: root.mutedColor
font.pixelSize: 10 }
                    Text { text: "Comment"
color: root.mutedColor
font.pixelSize: 10 }
                    TextField { id: metaGenre
Layout.fillWidth: true
text: root.metadataValues.genre || ""
placeholderText: "Genre"
color: root.textColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
onTextEdited: root.metadataValues.genre = text }
                    TextField { id: metaComment
Layout.fillWidth: true
text: root.metadataValues.comment || ""
placeholderText: "Comment"
color: root.textColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
onTextEdited: root.metadataValues.comment = text }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Button {
                        text: "Lookup on YouTube Music"
                        onClicked: backend.lookupYtMusicMetadata(metadataPath.text, metaArtist.text, metaTitle.text, metaAlbum.text)
                        background: Rectangle { radius: 11
color: root.accentSoftColor }
                        contentItem: Text { text: parent.text
color: root.accentColor
font.pixelSize: 10
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                    }
                    Button { text: "Read Tags"
onClicked: backend.inspectMediaFile(metadataPath.text)
background: Rectangle { radius: 11
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                    Button {
                        text: "Save Metadata"
                        onClicked: {
                            root.metadataValues = {path:metadataPath.text, title:metaTitle.text, artist:metaArtist.text, album:metaAlbum.text, date:metaDate.text, genre:metaGenre.text, comment:metaComment.text}
                            backend.saveMetadata(metadataPath.text, root.metadataValues)
                        }
                        background: Rectangle { radius: 11
color: "#3475EE" }
                        contentItem: Text { text: parent.text
color: "white"
font.bold: true
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    radius: 15
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    implicitHeight: batchMetadata.implicitHeight + 26
                    ColumnLayout {
                        id: batchMetadata
                        anchors.fill: parent
                        anchors.margins: 13
                        spacing: 8
                        Text { text: "BATCH FLAC METADATA + ARTWORK"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        Text { text: "Match each FLAC file against YouTube Music using contributing artist, title, and album. Review on a copy of your library first."
color: root.mutedColor
font.pixelSize: 10
wrapMode: Text.WordWrap
Layout.fillWidth: true }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField { id: metadataFolder
Layout.fillWidth: true
text: root.metadataFolderPath
placeholderText: "Folder containing FLAC files…"
color: root.textColor
placeholderTextColor: root.mutedColor
selectByMouse: true
onTextEdited: root.metadataFolderPath = text
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                            Button { text: "Browse"
onClicked: metadataFolderDialog.open()
background: Rectangle { radius: 10
color: root.panelColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 10
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                        }
                        Button {
                            text: "Rewrite Folder from YouTube Music"
                            Layout.preferredHeight: 39
                            onClicked: backend.rewriteFolderMetadata(metadataFolder.text)
                            background: Rectangle { radius: 10
color: "#3475EE" }
                            contentItem: Text { text: parent.text
color: "white"
font.pixelSize: 10
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                        }
                    }
                }
                Connections {
                    target: backend
                    function onMetadataLoaded(data) {
                        metadataPath.text = data.path || ""
                        metaTitle.text = data.title || ""
                        metaArtist.text = data.artist || ""
                        metaAlbum.text = data.album || ""
                        metaDate.text = data.date || ""
                        metaGenre.text = data.genre || ""
                        metaComment.text = data.comment || ""
                    }
                }
            }
        }
    }

    Component {
        id: coverPage
        Flickable {
            contentWidth: width
            contentHeight: coverContent.implicitHeight
            clip: true
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: coverContent
                width: parent.width
                spacing: 12
            Text { text: "Cover Art"
color: root.textColor
font.pixelSize: 24
font.bold: true }
            Text { text: "Embed a local image or image URL into audio or supported MKV files."
color: root.mutedColor
font.pixelSize: 11 }
            RowLayout {
                Layout.fillWidth: true
                TextField { id: coverMediaPath
Layout.fillWidth: true
text: root.coverMediaPathValue
onTextEdited: root.coverMediaPathValue = text
placeholderText: "Media file path"
color: root.textColor
placeholderTextColor: root.mutedColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                Button { text: "Browse media"
onClicked: coverMediaDialog.open()
background: Rectangle { radius: 10
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 10
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
            }
            RowLayout {
                Layout.fillWidth: true
                TextField { id: coverSource
Layout.fillWidth: true
text: root.coverSourcePath || root.metadataThumbnail
onTextEdited: root.coverSourcePath = text
placeholderText: "Image file path or https:// image URL"
color: root.textColor
placeholderTextColor: root.mutedColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                Button { text: "Browse image"
onClicked: coverImageDialog.open()
background: Rectangle { radius: 10
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 10
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 180
                radius: 16
                color: root.elevatedColor
                border.width: 1
                border.color: root.borderColor
                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    Text { anchors.horizontalCenter: parent.horizontalCenter
text: "▧"
color: root.accentColor
font.pixelSize: 33 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
text: "JPEG artwork embedding"
color: root.textColor
font.pixelSize: 15
font.bold: true }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
text: "FLAC · MP3 · M4A · MP4 · MKV and MOV covers"
color: root.mutedColor
font.pixelSize: 11 }
                }
            }
            Button {
                text: "Embed Artwork"
                Layout.preferredHeight: 43
                onClicked: backend.embedArtwork(coverMediaPath.text, coverSource.text)
                background: Rectangle { radius: 12
color: "#3475EE" }
                contentItem: Text { text: parent.text
color: "white"
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
            }
            Rectangle {
                Layout.fillWidth: true
                radius: 15
                color: root.elevatedColor
                border.width: 1
                border.color: root.borderColor
                implicitHeight: batchCovers.implicitHeight + 26
                ColumnLayout {
                    id: batchCovers
                    anchors.fill: parent
                    anchors.margins: 13
                    spacing: 8
                    Text { text: "BATCH COVER UPGRADE"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                    Text { text: "Find matching YouTube Music artwork and replace embedded FLAC covers."
color: root.mutedColor
font.pixelSize: 10
wrapMode: Text.WordWrap
Layout.fillWidth: true }
                    RowLayout {
                        Layout.fillWidth: true
                        TextField { id: coverFolder
Layout.fillWidth: true
text: root.coverFolderPath
placeholderText: "Folder containing FLAC files…"
color: root.textColor
placeholderTextColor: root.mutedColor
selectByMouse: true
onTextEdited: root.coverFolderPath = text
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                        Button { text: "Browse"
onClicked: coverFolderDialog.open()
background: Rectangle { radius: 10
color: root.panelColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 10
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                    }
                    Button {
                        text: "Upgrade Folder Covers"
                        Layout.preferredHeight: 39
                        onClicked: backend.upgradeFolderCovers(coverFolder.text)
                        background: Rectangle { radius: 10
color: "#3475EE" }
                        contentItem: Text { text: parent.text
color: "white"
font.pixelSize: 10
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                    }
                }
            }
            }
        }
    }

    Component {
        id: cropPage
        ColumnLayout {
            spacing: 12
            Text { text: "Crop Artwork"
color: root.textColor
font.pixelSize: 24
font.bold: true }
            Text { text: "Create a clean square JPEG using a center or edge-biased crop."
color: root.mutedColor
font.pixelSize: 11 }
            RowLayout {
                Layout.fillWidth: true
                TextField { id: cropSource
Layout.fillWidth: true
text: root.cropSourcePath
onTextEdited: root.cropSourcePath = text
placeholderText: "Source image path"
color: root.textColor
placeholderTextColor: root.mutedColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                Button { text: "Browse"
onClicked: cropImageDialog.open()
background: Rectangle { radius: 10
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Crop position"
color: root.mutedColor
font.pixelSize: 11 }
                ComboBox { id: cropPosition
model: ["Center", "Top", "Bottom", "Left", "Right"]
currentIndex: Math.max(0, model.indexOf(root.cropPositionValue))
onActivated: root.cropPositionValue = currentText
Layout.preferredWidth: 150
contentItem: Text { leftPadding: 11
text: cropPosition.displayText
color: root.textColor
font.pixelSize: 11
verticalAlignment: Text.AlignVCenter }
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 170
                radius: 16
                color: root.elevatedColor
                border.width: 1
                border.color: root.borderColor
                Column {
                    anchors.centerIn: parent
                    spacing: 9
                    Text { anchors.horizontalCenter: parent.horizontalCenter
text: "□"
color: root.accentColor
font.pixelSize: 37 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
text: "Square crop"
color: root.textColor
font.pixelSize: 16
font.bold: true }
                    Text { anchors.horizontalCenter: parent.horizontalCenter
text: "Saved as high-quality JPEG, quality 100."
color: root.mutedColor
font.pixelSize: 11 }
                }
            }
            Button {
                text: "Choose Output and Crop"
                Layout.preferredHeight: 43
                onClicked: cropSaveDialog.open()
                background: Rectangle { radius: 12
color: "#3475EE" }
                contentItem: Text { text: parent.text
color: "white"
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
            }
        }
    }

    Component {
        id: libraryPage
        ColumnLayout {
            spacing: 11
            Text { text: "Library Overhaul"
color: root.textColor
font.pixelSize: 24
font.bold: true }
            Text { text: "Scan a folder, review suggested titles, then apply changes deliberately."
color: root.mutedColor
font.pixelSize: 11 }
            RowLayout {
                Layout.fillWidth: true
                TextField { id: libraryPath
Layout.fillWidth: true
text: root.libraryFolder
placeholderText: "Choose media library folder…"
color: root.textColor
placeholderTextColor: root.mutedColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                Button { text: "Browse & Scan"
onClicked: libraryFolderDialog.open()
background: Rectangle { radius: 10
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 11
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
            }
            RowLayout {
                Layout.fillWidth: true
                Switch { id: rewriteTitlesSwitch
text: "Rewrite titles from filenames"
checked: false
onToggled: root.rewriteTitles = checked }
                Item { Layout.fillWidth: true }
                Text { text: root.libraryRows.length + " files"
color: root.mutedColor
font.pixelSize: 10 }
            }
            ListView {
                id: libraryList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 5
                model: root.libraryRows
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property var modelData
                    width: libraryList.width
                    height: 56
                    radius: 11
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 9
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: modelData.name
color: root.textColor
font.pixelSize: 10
font.bold: true
elide: Text.ElideRight
Layout.fillWidth: true }
                            Text { text: (modelData.title || "(no title)") + (modelData.removeAlbumArtist ? "  •  album-artist tag will be removed" : "")
color: root.mutedColor
font.pixelSize: 9
elide: Text.ElideRight
Layout.fillWidth: true }
                        }
                        Text { text: modelData.status
color: modelData.status === "Ready" ? root.successColor : "#D18B48"
font.pixelSize: 9 }
                    }
                }
                Rectangle {
                    anchors.centerIn: parent
                    visible: root.libraryRows.length === 0
                    width: Math.min(parent.width - 40, 360)
                    height: 95
                    radius: 15
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    Column {
                        anchors.centerIn: parent
                        spacing: 6
                        Text { anchors.horizontalCenter: parent.horizontalCenter
text: "♫"
color: root.accentColor
font.pixelSize: 26 }
                        Text { anchors.horizontalCenter: parent.horizontalCenter
text: "No scan results yet"
color: root.textColor
font.pixelSize: 13
font.bold: true }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Button {
                    text: "Apply Reviewed Changes"
                    Layout.preferredHeight: 42
                    enabled: root.libraryRows.length > 0
                    onClicked: backend.applyLibraryOverhaul(root.libraryRows, root.rewriteTitles)
                    background: Rectangle { radius: 12
color: parent.enabled ? "#3475EE" : root.borderColor }
                    contentItem: Text { text: parent.text
color: parent.enabled ? "white" : root.mutedColor
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                }
                Button {
                    text: "Full FLAC Overhaul…"
                    Layout.preferredHeight: 42
                    enabled: root.libraryFolder.length > 0
                    onClicked: confirmFullOverhaulDialog.open()
                    background: Rectangle { radius: 12
color: parent.enabled ? (root.darkMode ? "#5A3A16" : "#FFF0D8") : root.borderColor
border.width: 1
border.color: root.darkMode ? "#85521D" : "#E6C28A" }
                    contentItem: Text { text: parent.text
color: parent.enabled ? (root.darkMode ? "#FFD08A" : "#8A4E00") : root.mutedColor
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter }
                }
            }
        }
    }

    Component {
        id: settingsPage
        Flickable {
            contentWidth: width
            contentHeight: settingsContent.implicitHeight
            clip: true
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: settingsContent
                width: parent.width
                spacing: 14
                Text { text: "Settings"
color: root.textColor
font.pixelSize: 24
font.bold: true }
                Text { text: "These choices are saved to your existing toolkit configuration file."
color: root.mutedColor
font.pixelSize: 11 }
                Rectangle {
                    Layout.fillWidth: true
                    radius: 15
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    implicitHeight: outputSettings.implicitHeight + 26
                    ColumnLayout {
                        id: outputSettings
                        anchors.fill: parent
                        anchors.margins: 13
                        spacing: 8
                        Text { text: "DOWNLOAD LOCATION"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField { id: settingsOutputPath
Layout.fillWidth: true
text: root.downloadDirectory
readOnly: true
color: root.textColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                            Button { text: "Choose"
onClicked: outputFolderDialog.open()
background: Rectangle { radius: 10
color: root.accentSoftColor }
contentItem: Text { text: parent.text
color: root.accentColor
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    radius: 15
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    implicitHeight: cookieSettings.implicitHeight + 26
                    ColumnLayout {
                        id: cookieSettings
                        anchors.fill: parent
                        anchors.margins: 13
                        spacing: 8
                        Text { text: "YOUTUBE SESSION"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        Text { Layout.fillWidth: true
text: root.hasCookies ? "Cookie file configured: " + root.cookiePath : "No cookies.txt file configured. Public videos may still work."
color: root.hasCookies ? root.successColor : "#D18B48"
font.pixelSize: 10
wrapMode: Text.WrapAnywhere }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField { id: settingsCookiePath
Layout.fillWidth: true
text: root.cookiePath
placeholderText: "Netscape-format cookies.txt path"
color: root.textColor
placeholderTextColor: root.mutedColor
background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor } }
                            Button { text: "Browse"
onClicked: cookieFileDialog.open()
background: Rectangle { radius: 10
color: root.accentSoftColor }
contentItem: Text { text: parent.text
color: root.accentColor
font.pixelSize: 11
font.bold: true
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                        }
                        Button { text: "Save Cookie Path"
onClicked: backend.setCookieFile(settingsCookiePath.text)
background: Rectangle { radius: 10
color: root.panelColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 10
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        Text { text: "PERFORMANCE"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        ComboBox {
                            id: performanceBox
                            Layout.fillWidth: true
                            model: ["conservative", "balanced", "aggressive"]
                            currentIndex: Math.max(0, model.indexOf(root.performanceMode))
                            onActivated: backend.setPerformanceMode(currentText)
                            contentItem: Text { leftPadding: 11
text: performanceBox.displayText
color: root.textColor
font.pixelSize: 11
verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Text { text: "EXISTING FILES"
color: root.mutedColor
font.pixelSize: 9
font.bold: true
font.letterSpacing: 1 }
                        ComboBox {
                            id: conflictBox
                            Layout.fillWidth: true
                            model: ["rename", "skip", "replace"]
                            currentIndex: Math.max(0, model.indexOf(root.conflictMode))
                            onActivated: backend.setConflictMode(currentText)
                            contentItem: Text { leftPadding: 11
text: conflictBox.displayText
color: root.textColor
font.pixelSize: 11
verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { radius: 10
color: root.inputColor
border.width: 1
border.color: root.borderColor }
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    radius: 14
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    implicitHeight: aboutText.implicitHeight + 24
                    Text {
                        id: aboutText
                        anchors.fill: parent
                        anchors.margins: 12
                        text: "Architecture: Qt Quick/QML owns the interface and animations; Python runs yt-dlp, metadata, artwork, queue and file operations on worker threads. This is still a migration branch: test against copies of your media before using bulk operations."
                        color: root.mutedColor
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }

    Component {
        id: activityPage
        ColumnLayout {
            spacing: 11
            Text { text: "Activity Log"
color: root.textColor
font.pixelSize: 24
font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Backend messages and download progress diagnostics."
color: root.mutedColor
font.pixelSize: 11 }
                Item { Layout.fillWidth: true }
                Button { text: "Clear"
onClicked: root.logText = ""
background: Rectangle { radius: 9
color: root.elevatedColor
border.width: 1
border.color: root.borderColor }
contentItem: Text { text: parent.text
color: root.textColor
font.pixelSize: 10
horizontalAlignment: Text.AlignHCenter
verticalAlignment: Text.AlignVCenter } }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                TextArea {
                    text: root.logText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: root.textColor
                    font.family: "Consolas"
                    font.pixelSize: 10
                    background: Rectangle { radius: 13
color: root.inputColor
border.width: 1
border.color: root.borderColor }
                }
            }
        }
    }
}
