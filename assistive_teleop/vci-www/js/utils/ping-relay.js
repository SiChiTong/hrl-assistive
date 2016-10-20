var RFH = (function(module) {
    module.PingRelay = function (options) {
    'use strict';
    var ros = options.ros;
    var inTopic = options.inTopic;
    var outTopic = options.outTopic;
    
    ros.getMsgDetails('assistive_teleop/Ping');
    var relayPub = new ROSLIB.Topic({
        ros: ros,
        name: outTopic,
        messageType: 'assistive_teleop/Ping'
    });
    relayPub.advertise();

    var stampAndReturn = function (pingMsg) {
        var ms = new Date().getTime();
        var s = Math.round(ms / 1000);
        var ns = (ms - 1000*s) * 1000000;
        pingMsg.recv_time.secs = s;
        pingMsg.recv_time.nsecs = ns;
        relayPub.publish(pingMsg);
    };

    var relaySub = new ROSLIB.Topic({
        ros: ros,
        name: inTopic,
        messageType: 'assistive_teleop/Ping'
    });
    relaySub.subscribe(stampAndReturn);
    };
    return module;
})(RFH || {});
