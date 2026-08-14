import QtQuick

Rectangle {
    id: root
    color: "#181926"

    property int stage

    onStageChanged: {
        bar.width = Math.max(8, (200 * stage) / 6)
    }

    Image {
        id: logo
        anchors.centerIn: parent
        source: "images/mark.png"
        sourceSize.width: 128
        sourceSize.height: 128
        asynchronous: true
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: logo.bottom
        anchors.topMargin: 28
        width: 200
        height: 3
        radius: 1
        color: "#363a4f"

        Rectangle {
            id: bar
            width: 8
            height: parent.height
            radius: 1
            color: "#c6a0f6"
            Behavior on width {
                NumberAnimation { duration: 240; easing.type: Easing.InOutQuad }
            }
        }
    }
}
