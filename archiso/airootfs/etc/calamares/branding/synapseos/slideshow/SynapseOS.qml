import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 20000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Image {
            id: slide1a
            source: "slide1.png"
            width: 480
            height: 300
            fillMode: Image.PreserveAspectFit
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Slide {
        Image {
            id: slide2a
            source: "slide2.png"
            width: 480
            height: 300
            fillMode: Image.PreserveAspectFit
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Slide {
        Image {
            id: slide3a
            source: "slide3.png"
            width: 480
            height: 300
            fillMode: Image.PreserveAspectFit
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Slide {
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Installation complete. Reboot into SynapseOS and enjoy the COSMIC desktop.")
            wrapMode: Text.WordWrap
            width: 480
            horizontalAlignment: Text.AlignHCenter
            color: "#e8eef7"
            font.pixelSize: 22
        }
    }
}