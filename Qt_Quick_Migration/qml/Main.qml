import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1180
    height: 780
    minimumWidth: 900
    minimumHeight: 620
    visible: true
    title: "YouTube Toolkit — Qt Quick Preview"

    property bool darkMode: true
    property int currentPage: 0
    property bool introComplete: false
    property string statusMessage: "Qt Quick preview ready — download engine not connected"
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
    property var navItems: [
        { title: "Downloader", icon: "↓", detail: "Download media" },
        { title: "Queue", icon: "≡", detail: "Manage tasks" },
        { title: "Metadata", icon: "✎", detail: "Edit tags" },
        { title: "Cover Art", icon: "▧", detail: "Update artwork" },
        { title: "Crop Art", icon: "□", detail: "Prepare covers" },
        { title: "Library Overhaul", icon: "♫", detail: "Organize library" }
    ]
    property var pageComponents: [
        downloaderPage,
        queuePage,
        metadataPage,
        coverPage,
        cropPage,
        libraryPage
    ]

    background: Rectangle {
        color: root.bgColor
        Behavior on color { ColorAnimation { duration: 280; easing.type: Easing.OutCubic } }
    }

    function pageChanged() {
        if (!introComplete)
            return
        pageLoader.opacity = 0
        pageLoader.y = 13
        pageLoader.scale = 0.99
        pageEnter.restart()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 16

        Rectangle {
            id: header
            Layout.fillWidth: true
            Layout.preferredHeight: 88
            radius: 22
            color: root.panelColor
            border.width: 1
            border.color: root.borderColor
            opacity: 0
            y: -8

            Behavior on color { ColorAnimation { duration: 280; easing.type: Easing.OutCubic } }
            Behavior on border.color { ColorAnimation { duration: 280 } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 19
                anchors.rightMargin: 18
                spacing: 13

                Rectangle {
                    Layout.preferredWidth: 49
                    Layout.preferredHeight: 49
                    radius: 16
                    color: root.accentSoftColor
                    border.width: 1
                    border.color: root.borderColor
                    Behavior on color { ColorAnimation { duration: 280 } }

                    Text {
                        anchors.centerIn: parent
                        text: "♫"
                        color: root.accentColor
                        font.pixelSize: 26
                        font.bold: true
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        text: "YouTube Toolkit"
                        color: root.textColor
                        font.family: "Segoe UI"
                        font.pixelSize: 21
                        font.bold: true
                    }
                    Text {
                        text: "Media downloads, metadata & artwork"
                        color: root.mutedColor
                        font.family: "Segoe UI"
                        font.pixelSize: 12
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 104
                    Layout.preferredHeight: 30
                    radius: 15
                    color: root.darkMode ? "#142B26" : "#E4F6EC"
                    border.width: 1
                    border.color: root.darkMode ? "#285345" : "#C4E8D2"
                    Behavior on color { ColorAnimation { duration: 280 } }

                    Row {
                        anchors.centerIn: parent
                        spacing: 7
                        Rectangle {
                            width: 6
                            height: 6
                            radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: "#43D99A"
                        }
                        Text {
                            text: "UI PREVIEW"
                            color: root.darkMode ? "#7AE2B5" : "#218653"
                            font.pixelSize: 10
                            font.bold: true
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                Button {
                    id: themeButton
                    Layout.preferredWidth: 42
                    Layout.preferredHeight: 42
                    text: root.darkMode ? "☼" : "☾"
                    onClicked: root.darkMode = !root.darkMode

                    background: Rectangle {
                        radius: 14
                        color: themeButton.down ? root.accentSoftColor : themeButton.hovered ? root.hoverColor : root.elevatedColor
                        border.width: 1
                        border.color: root.borderColor
                        Behavior on color { ColorAnimation { duration: 220 } }
                        Behavior on border.color { ColorAnimation { duration: 220 } }
                    }
                    contentItem: Text {
                        text: themeButton.text
                        color: root.textColor
                        font.pixelSize: 21
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    scale: down ? 0.94 : 1.0
                    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                    ToolTip.visible: hovered
                    ToolTip.text: "Toggle appearance"
                }
            }
        }

        ParallelAnimation {
            id: headerIntro
            NumberAnimation { target: header; property: "opacity"; from: 0; to: 1; duration: 380; easing.type: Easing.OutCubic }
            NumberAnimation { target: header; property: "y"; from: -8; to: 0; duration: 420; easing.type: Easing.OutCubic }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            Rectangle {
                id: navigation
                Layout.preferredWidth: 214
                Layout.minimumWidth: 185
                Layout.fillHeight: true
                radius: 22
                color: root.panelColor
                border.width: 1
                border.color: root.borderColor
                Behavior on color { ColorAnimation { duration: 280; easing.type: Easing.OutCubic } }
                Behavior on border.color { ColorAnimation { duration: 280 } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.topMargin: 17
                    anchors.bottomMargin: 16
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 7

                    Text {
                        text: "WORKSPACE"
                        color: root.mutedColor
                        font.pixelSize: 10
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
                            Layout.preferredHeight: 47

                            Rectangle {
                                anchors.fill: parent
                                radius: 13
                                color: root.currentPage === navItem.index ? root.accentSoftColor : navMouse.containsMouse ? root.hoverColor : "transparent"
                                Behavior on color { ColorAnimation { duration: 180; easing.type: Easing.OutCubic } }
                            }

                            Rectangle {
                                width: 3
                                height: 22
                                radius: 2
                                anchors.left: parent.left
                                anchors.leftMargin: 1
                                anchors.verticalCenter: parent.verticalCenter
                                color: root.accentColor
                                opacity: root.currentPage === navItem.index ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 180 } }
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 13
                                anchors.rightMargin: 9
                                spacing: 11

                                Text {
                                    text: navItem.modelData.icon
                                    color: root.currentPage === navItem.index ? root.accentColor : root.mutedColor
                                    font.pixelSize: 18
                                    Layout.preferredWidth: 22
                                    horizontalAlignment: Text.AlignHCenter
                                    Behavior on color { ColorAnimation { duration: 180 } }
                                }

                                Text {
                                    text: navItem.modelData.title
                                    color: root.currentPage === navItem.index ? root.textColor : root.mutedColor
                                    font.pixelSize: 12
                                    font.bold: root.currentPage === navItem.index
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                    Behavior on color { ColorAnimation { duration: 180 } }
                                }
                            }

                            MouseArea {
                                id: navMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.currentPage = navItem.index
                            }

                            scale: navMouse.pressed ? 0.975 : 1
                            Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
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
                        Behavior on color { ColorAnimation { duration: 280 } }

                        Column {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 5
                            Text {
                                text: "Qt Quick engine"
                                color: root.textColor
                                font.pixelSize: 12
                                font.bold: true
                            }
                            Text {
                                text: "Animation prototype"
                                color: root.mutedColor
                                font.pixelSize: 11
                            }
                            Text {
                                text: "Backend: disconnected"
                                color: "#E5A54B"
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: contentPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 22
                color: root.panelColor
                border.width: 1
                border.color: root.borderColor
                clip: true
                Behavior on color { ColorAnimation { duration: 280; easing.type: Easing.OutCubic } }
                Behavior on border.color { ColorAnimation { duration: 280 } }

                Loader {
                    id: pageLoader
                    anchors.fill: parent
                    anchors.margins: 23
                    sourceComponent: root.pageComponents[root.currentPage]
                    opacity: 1
                    scale: 1
                    y: 0
                }

                ParallelAnimation {
                    id: pageEnter
                    NumberAnimation { target: pageLoader; property: "opacity"; from: 0; to: 1; duration: 300; easing.type: Easing.OutCubic }
                    NumberAnimation { target: pageLoader; property: "y"; from: 13; to: 0; duration: 340; easing.type: Easing.OutCubic }
                    NumberAnimation { target: pageLoader; property: "scale"; from: 0.99; to: 1; duration: 340; easing.type: Easing.OutCubic }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            spacing: 8

            Rectangle {
                width: 6
                height: 6
                radius: 3
                color: "#43D99A"
                Layout.alignment: Qt.AlignVCenter
            }

            Text {
                Layout.fillWidth: true
                text: root.statusMessage
                color: root.mutedColor
                font.pixelSize: 10
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }

            Text {
                text: "QT QUICK • PROTOTYPE"
                color: root.mutedColor
                font.pixelSize: 9
                font.bold: true
                font.letterSpacing: 1
            }
        }
    }

    Connections {
        target: bridge
        function onStatusChanged(message) {
            root.statusMessage = message
        }
    }

    onCurrentPageChanged: pageChanged()

    Component.onCompleted: {
        introComplete = true
        headerIntro.start()
    }

    Component {
        id: downloaderPage

        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 16

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: "Downloader"
                        color: root.textColor
                        font.pixelSize: 25
                        font.bold: true
                    }
                    Text {
                        text: "Grab audio and video while keeping the workflow simple."
                        color: root.mutedColor
                        font.pixelSize: 12
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 246
                    radius: 18
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    Behavior on color { ColorAnimation { duration: 280 } }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 19
                        spacing: 13

                        Text {
                            text: "SOURCE"
                            color: root.mutedColor
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 1.2
                        }

                        TextField {
                            id: urlField
                            Layout.fillWidth: true
                            Layout.preferredHeight: 48
                            placeholderText: "Paste a YouTube or YouTube Music URL..."
                            color: root.textColor
                            placeholderTextColor: root.mutedColor
                            font.pixelSize: 12
                            selectByMouse: true
                            onAccepted: bridge.previewAction(text, qualityBox.currentText)

                            background: Rectangle {
                                radius: 13
                                color: root.inputColor
                                border.width: urlField.activeFocus ? 1.5 : 1
                                border.color: urlField.activeFocus ? root.accentColor : root.borderColor
                                Behavior on color { ColorAnimation { duration: 240 } }
                                Behavior on border.color { ColorAnimation { duration: 160 } }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text {
                                    text: "QUALITY CEILING"
                                    color: root.mutedColor
                                    font.pixelSize: 10
                                    font.bold: true
                                    font.letterSpacing: 1
                                }

                                ComboBox {
                                    id: qualityBox
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 43
                                    model: ["Best available", "2160p (4K)", "1440p", "1080p", "720p", "480p", "Audio only"]
                                    currentIndex: 3
                                    contentItem: Text {
                                        leftPadding: 13
                                        rightPadding: 28
                                        text: qualityBox.displayText
                                        color: root.textColor
                                        font.pixelSize: 12
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }
                                    background: Rectangle {
                                        radius: 12
                                        color: root.inputColor
                                        border.width: 1
                                        border.color: qualityBox.popup.visible ? root.accentColor : root.borderColor
                                        Behavior on color { ColorAnimation { duration: 240 } }
                                    }
                                    delegate: ItemDelegate {
                                        width: qualityBox.width
                                        contentItem: Text {
                                            text: modelData
                                            color: root.textColor
                                            font.pixelSize: 12
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        background: Rectangle {
                                            color: highlighted ? root.accentSoftColor : root.panelColor
                                        }
                                    }
                                    popup: Popup {
                                        y: qualityBox.height + 4
                                        width: qualityBox.width
                                        implicitHeight: contentItem.implicitHeight
                                        padding: 5
                                        contentItem: ListView {
                                            clip: true
                                            implicitHeight: contentHeight
                                            model: qualityBox.popup.visible ? qualityBox.delegateModel : null
                                            currentIndex: qualityBox.highlightedIndex
                                            ScrollIndicator.vertical: ScrollIndicator {}
                                        }
                                        background: Rectangle {
                                            radius: 12
                                            color: root.panelColor
                                            border.width: 1
                                            border.color: root.borderColor
                                        }
                                    }
                                }
                            }

                            ColumnLayout {
                                Layout.preferredWidth: 160
                                spacing: 6
                                Text {
                                    text: "OUTPUT"
                                    color: root.mutedColor
                                    font.pixelSize: 10
                                    font.bold: true
                                    font.letterSpacing: 1
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 43
                                    radius: 12
                                    color: root.inputColor
                                    border.width: 1
                                    border.color: root.borderColor
                                    Row {
                                        anchors.centerIn: parent
                                        spacing: 7
                                        Text { text: "♫"; color: root.accentColor; font.pixelSize: 15 }
                                        Text { text: "FLAC / MKV"; color: root.textColor; font.pixelSize: 11; font.bold: true }
                                    }
                                }
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 82
                        radius: 16
                        color: root.elevatedColor
                        border.width: 1
                        border.color: root.borderColor
                        Behavior on color { ColorAnimation { duration: 280 } }
                        Column {
                            anchors.fill: parent
                            anchors.margins: 13
                            spacing: 4
                            Text { text: "SMART FORMAT FALLBACK"; color: root.mutedColor; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.7 }
                            Text { text: "Try the chosen ceiling, then use the best available match."; color: root.textColor; font.pixelSize: 11; wrapMode: Text.WordWrap; width: parent.width }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 82
                        radius: 16
                        color: root.elevatedColor
                        border.width: 1
                        border.color: root.borderColor
                        Behavior on color { ColorAnimation { duration: 280 } }
                        Column {
                            anchors.fill: parent
                            anchors.margins: 13
                            spacing: 4
                            Text { text: "TEMP FILES"; color: root.mutedColor; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.7 }
                            Text { text: "Scratch data will stay isolated in tempytm."; color: root.textColor; font.pixelSize: 11; wrapMode: Text.WordWrap; width: parent.width }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Button {
                        id: previewButton
                        text: "Preview UI action  →"
                        Layout.preferredWidth: 185
                        Layout.preferredHeight: 46
                        onClicked: bridge.previewAction(urlField.text, qualityBox.currentText)
                        background: Rectangle {
                            radius: 14
                            color: previewButton.down ? "#2859B9" : previewButton.hovered ? "#4C83F3" : "#3475EE"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                        contentItem: Text {
                            text: previewButton.text
                            color: "#FFFFFF"
                            font.pixelSize: 12
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        scale: down ? 0.975 : 1
                        Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Prototype only — this button does not start a download."
                        color: root.mutedColor
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }

    Component {
        id: queuePage
        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 15
                Text { text: "Queue"; color: root.textColor; font.pixelSize: 25; font.bold: true }
                Text { text: "A future home for active, pending, and completed jobs."; color: root.mutedColor; font.pixelSize: 12 }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 18
                    color: root.elevatedColor
                    border.width: 1
                    border.color: root.borderColor
                    Column {
                        anchors.centerIn: parent
                        spacing: 9
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "≡"; color: root.accentColor; font.pixelSize: 34 }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Queue view"; color: root.textColor; font.pixelSize: 17; font.bold: true }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "The existing queue engine will be connected after the UI is validated."; color: root.mutedColor; font.pixelSize: 11 }
                    }
                }
            }
        }
    }

    Component {
        id: metadataPage
        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 15
                Text { text: "Metadata"; color: root.textColor; font.pixelSize: 25; font.bold: true }
                Text { text: "Inspect and rewrite tags without leaving the toolkit."; color: root.mutedColor; font.pixelSize: 12 }
                PlaceholderCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    heading: "Tag editor"
                    symbol: "✎"
                    description: "The existing mutagen-based metadata workflow will be connected here."
                }
            }
        }
    }

    Component {
        id: coverPage
        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 15
                Text { text: "Cover Art"; color: root.textColor; font.pixelSize: 25; font.bold: true }
                Text { text: "Update embedded artwork for supported audio formats."; color: root.mutedColor; font.pixelSize: 12 }
                PlaceholderCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    heading: "Artwork updater"
                    symbol: "▧"
                    description: "Cover lookup, download, and embedding will remain in Python behind this QML interface."
                }
            }
        }
    }

    Component {
        id: cropPage
        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 15
                Text { text: "Crop Art"; color: root.textColor; font.pixelSize: 25; font.bold: true }
                Text { text: "Prepare square artwork and previews."; color: root.mutedColor; font.pixelSize: 12 }
                PlaceholderCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    heading: "Artwork cropper"
                    symbol: "□"
                    description: "The crop controls and image processing will be ported once the new window shell is stable."
                }
            }
        }
    }

    Component {
        id: libraryPage
        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 15
                Text { text: "Library Overhaul"; color: root.textColor; font.pixelSize: 25; font.bold: true }
                Text { text: "Batch organization and media-library maintenance."; color: root.mutedColor; font.pixelSize: 12 }
                PlaceholderCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    heading: "Library tools"
                    symbol: "♫"
                    description: "The existing pipeline will be connected here incrementally; no backend behavior is replaced in this prototype."
                }
            }
        }
    }

    component PlaceholderCard: Rectangle {
        property string heading: "Coming soon"
        property string symbol: "✦"
        property string description: ""
        radius: 18
        color: root.elevatedColor
        border.width: 1
        border.color: root.borderColor
        Behavior on color { ColorAnimation { duration: 280 } }

        Column {
            anchors.centerIn: parent
            width: Math.min(parent.width - 60, 440)
            spacing: 10

            Rectangle {
                width: 58
                height: 58
                radius: 18
                color: root.accentSoftColor
                anchors.horizontalCenter: parent.horizontalCenter
                Behavior on color { ColorAnimation { duration: 280 } }
                Text {
                    anchors.centerIn: parent
                    text: parent.parent.parent.symbol
                    color: root.accentColor
                    font.pixelSize: 27
                }
            }
            Text {
                text: parent.parent.heading
                anchors.horizontalCenter: parent.horizontalCenter
                color: root.textColor
                font.pixelSize: 17
                font.bold: true
            }
            Text {
                width: parent.width
                text: parent.parent.description
                anchors.horizontalCenter: parent.horizontalCenter
                color: root.mutedColor
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                text: "QML interface prototype"
                anchors.horizontalCenter: parent.horizontalCenter
                color: root.accentColor
                font.pixelSize: 10
                font.bold: true
            }
        }
    }
}
