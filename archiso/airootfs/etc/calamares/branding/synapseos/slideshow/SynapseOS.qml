import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    function onActivate() {
        presentation.currentSlide = 0
    }

    function onLeave() {
    }

    Timer {
        interval: 16000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Image {
            anchors.fill: parent
            source: "slide1.png"
            fillMode: Image.PreserveAspectCrop
        }
    }

    Slide {
        Image {
            anchors.fill: parent
            source: "slide2.png"
            fillMode: Image.PreserveAspectCrop
        }
    }

    Slide {
        Image {
            anchors.fill: parent
            source: "slide3.png"
            fillMode: Image.PreserveAspectCrop
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#181926"
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("Installation complete.\nReboot into SynapseOS and enjoy Plasma.")
            wrapMode: Text.WordWrap
            width: Math.min(parent.width - 80, 640)
            horizontalAlignment: Text.AlignHCenter
            color: "#cad3f5"
            font.pixelSize: 26
            lineHeight: 1.25
        }
    }
}
