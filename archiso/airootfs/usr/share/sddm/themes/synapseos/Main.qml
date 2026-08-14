import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
  id: root
  width: 640
  height: 480
  color: "#181926"

  property string currentUser: userModel.lastUser
  property bool loginFailed: false
  property bool needUser: currentUser === undefined || currentUser === ""
  property int sessionIndex: {
    var plasma = -1
    for (var i = 0; i < sessionModel.rowCount(); i++) {
      var name = (sessionModel.data(sessionModel.index(i, 0), Qt.DisplayRole) || "").toString().toLowerCase()
      if (name.indexOf("plasma") !== -1)
        return i
    }
    return sessionModel.lastIndex
  }

  function submit() {
    if (root.needUser)
      root.currentUser = username.text
    if (root.currentUser === "" || password.text === "")
      return
    sddm.login(root.currentUser, password.text, root.sessionIndex)
  }

  Connections {
    target: sddm
    function onLoginFailed() {
      root.loginFailed = true
      password.text = ""
      password.focus = true
    }
    function onLoginSucceeded() {
      root.loginFailed = false
    }
  }

  Column {
    anchors.centerIn: parent
    spacing: 36

    Image {
      id: logo
      source: "logo.png"
      width: Math.min(sourceSize.width, root.width * 0.72)
      height: sourceSize.width > 0 ? Math.round(width * sourceSize.height / sourceSize.width) : 0
      fillMode: Image.PreserveAspectFit
      anchors.horizontalCenter: parent.horizontalCenter
    }

    Item {
      visible: root.needUser
      width: entry.width
      height: entry.height
      anchors.horizontalCenter: parent.horizontalCenter
      Image {
        source: "entry.png"
        anchors.fill: parent
      }
      TextInput {
        id: username
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        color: "#cad3f5"
        font.family: "Inter"
        font.pixelSize: 16
        horizontalAlignment: TextInput.AlignHCenter
        verticalAlignment: TextInput.AlignVCenter
        clip: true
        onAccepted: password.forceActiveFocus()
      }
      Text {
        anchors.fill: username
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        text: "user"
        color: "#6e738d"
        font.family: "Inter"
        font.pixelSize: 16
        visible: username.text.length === 0 && !username.activeFocus
      }
    }

    Row {
      anchors.horizontalCenter: parent.horizontalCenter
      spacing: 14

      Image {
        source: root.loginFailed ? "lock-failed.png" : "lock.png"
        width: 28
        height: 32
        fillMode: Image.PreserveAspectFit
        anchors.verticalCenter: parent.verticalCenter
      }

      Item {
        width: entry.width
        height: entry.height

        Image {
          id: entry
          source: root.loginFailed ? "entry-failed.png" : "entry.png"
          anchors.centerIn: parent
        }

        Row {
          anchors.left: parent.left
          anchors.leftMargin: 20
          anchors.verticalCenter: parent.verticalCenter
          spacing: 5
          Repeater {
            model: Math.min(password.text.length, 21)
            Image {
              source: "bullet.png"
              width: 7
              height: 7
            }
          }
        }

        TextInput {
          id: password
          anchors.fill: parent
          anchors.leftMargin: 20
          anchors.rightMargin: 20
          verticalAlignment: TextInput.AlignVCenter
          echoMode: TextInput.Password
          font.family: "JetBrainsMono Nerd Font"
          font.pixelSize: 22
          font.letterSpacing: 4
          passwordCharacter: "\u2022"
          color: "transparent"
          selectionColor: "transparent"
          selectedTextColor: "transparent"
          cursorDelegate: Item {}
          focus: true
          onTextChanged: root.loginFailed = false
          Keys.onPressed: function (event) {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
              root.submit()
              event.accepted = true
            }
          }
        }
      }
    }
  }

  Column {
    anchors.left: parent.left
    anchors.bottom: parent.bottom
    anchors.margins: 28
    spacing: 10

    Text {
      text: "⏻"
      color: "#a5adcb"
      font.pixelSize: 18
      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: sddm.powerOff()
      }
    }
    Text {
      text: "↺"
      color: "#a5adcb"
      font.pixelSize: 18
      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: sddm.reboot()
      }
    }
  }

  Component.onCompleted: {
    if (root.needUser)
      username.forceActiveFocus()
    else
      password.forceActiveFocus()
  }
}
