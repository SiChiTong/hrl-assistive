var FITTS = {
    setup: function () {
        var startFittsLaw = function () {
            var dwellDelay = $('#dwellTimeInput').val();
            var test = new FittsLawTest({dwellTime: dwellDelay});
            $('#testArea').empty();
//            $('#startButton').remove();
 //           $('form').remove();
            test.run();
        }

        $('button.startButton').button().on('click', startFittsLaw);
    }
};


var FittsLawTest = function (options) {
    'use strict';
    options = options || {};
    var self = this;
    var dwellTime = options.dwellTime || 0;
    var $targetArea = $('#testArea');
    var setParameters = [];
    var targetSets = [];
    var targets = [];
    var dataSets = [];
    var data = [];
    var liveTarget = null;
    var targetDistance = null;
    var endTime;
    var startTime;

    var shuffleArray = function (array) {
        var currentIndex = array.length;
        var randInd, tmp;
        while (0 !== currentIndex) {
            var randInd = Math.floor(Math.random() * currentIndex);
            currentIndex -= 1;
            tmp = array[currentIndex];
            array[currentIndex] = array[randInd];
            array[randInd] = tmp;
        }
    };

    var sphericalTargets = function () {
        var h = $targetArea.height();
        var w =  $targetArea.width();
        var cx = w/2;
        var cy = h/2;
        var widths = [20,60,100];
        var lim = Math.min(h, w)/2 - 0.75*widths[widths.length-1];
        var ringDiameters = [0.33*lim, 0.67*lim, lim]; 
        var n = 25;
        var targetSets = [];
        for (var iw=0; iw < widths.length; iw +=1) {
            for (var id=0; id < ringDiameters.length; id +=1) {
                setParameters.push([ringDiameters[id], widths[iw]]);
            }
        }
        shuffleArray(setParameters); // Randomize the order of cases
        for (var i=0; i<setParameters.length; i += 1) {
            targetSets.push(targetRing(cx, cy, n, setParameters[i][0], setParameters[i][1]));
        }
        return targetSets;
    };

    var ringIndexOrders = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25];
    var targetRing = function (cx, cy, n, diameter, width) {
        var angle, tx, ty, div;
        var targets = [];
        var css = {display: 'block',
                   position: 'absolute',
                   height: width+'px',
                   width: width+'px',
                   top: cy,
                   left: cx,
                   }
        for (var i=0; i<=n; i+=1) {
           angle = (2*Math.PI / n) * i + Math.PI;
           tx = cx + diameter * Math.sin(angle);
           ty = cy + diameter * Math.cos(angle);
           css['top'] = ty - width/2 + 'px';
           css['left'] = tx - width/2 + 'px';
           div = $("<div/>", {"class":"target sphere"}).css(css).hide();
           targets[ringIndexOrders[i]] = div;
           $targetArea.append(div);
        };
        return targets;
    };

    var timeDifferenceMS = function (date1, date2) {
       var dH = date2.getHours() - date1.getHours();
       var dM = date2.getMinutes() - date1.getMinutes();
       var dS = date2.getSeconds() - date1.getSeconds();
       var dMS = date2.getMilliseconds() - date1.getMilliseconds();
       var timeDiff = dMS + 1000*dS + 60*1000*dM + 60*60*1000*dH;
       var withoutDwell = timeDiff - dwellTime;
       return withoutDwell;
    };

    var responseCB = function (event) {
        var clickTime = new Date();
        if (liveTarget.fittsData['startTime'] === undefined) { return; } // Probably haven't moved, just ignore the click...
        liveTarget.fittsData['endTime'] = clickTime;
        liveTarget.fittsData['duration'] = timeDifferenceMS(liveTarget.fittsData['startTime'], clickTime);
        liveTarget.fittsData['endXY'] = [event.pageX, event.pageY];
        data.push(liveTarget.fittsData);
        liveTarget.remove(); 
        nextTarget();
    };
    
    var recordStart = function (event) {
        liveTarget.fittsData['startTime'] = new Date();
        liveTarget.fittsData['startXY'] = [event.pageX, event.pageY];
    };

    var nextTarget = function () {
        if (targets.length <= 0) {
            newTargetSet();    
            return;
        }
        liveTarget = targets.pop(0);
        liveTarget.fittsData = {};
        $targetArea.one('mousemove', recordStart);
        liveTarget.show();
        var pos = liveTarget.position();
        var w = liveTarget.width();
        var h = liveTarget.height();
        liveTarget.fittsData['width'] = w; // Assumes circular target
        liveTarget.fittsData['goalXY'] = [pos['left']+w/2, pos['top']+h/2];
    }

    var newTargetSet = function () {
        if (data.length > 0) { // Add data from last set and clear for all but first call
            dataSets.push(data);
            data = [];
        }
        if (targetSets.length <= 0) {
            endTime = new Date();
            $targetArea.off('mousedown').css({'background-color':'orange'});
            finishAnalysis();
        } else {
            $targetArea.off('mousedown');
            $nextRoundButton.show();
            targets = targetSets.pop();
        }
    };
    
    var startRound = function () {
        $nextRoundButton.hide();
        $targetArea.on('mousedown', responseCB);
        nextTarget();
    };

    var $nextRoundButton = $('<button class="startButton">Start Next Round</button>').button().on('click', startRound).hide().css({bottom:'initial', top:'50%'});
    
    self.run = function () {
        targetSets = sphericalTargets(); 
        targets = targetSets.pop();
        $targetArea.append($nextRoundButton);
        startTime = new Date();
        startRound();
    };

    var removeOutliers = function (data) {
        var distances = getDistances(data);
        var times = getTimes(data);
        var timeMean = math.mean(times);
        var timeStd = math.std(times);
        var minTime = timeMean - 3*timeStd; 
        var maxTime = timeMean + 3*timeStd;
        var distMean = math.mean(distances);
        var distStd = math.std(distances)
        var minDist = distMean - 3*distStd;
        var maxDist = distMean + 3*distStd;
        var timeMinOutliers = math.smaller(times, minTime);
        var timeMaxOutliers = math.larger(times, maxTime);
        var distMinOutliers = math.smaller(distances, minDist);
        var distMaxOutliers = math.larger(distances, maxDist);
        var outliers = math.or(timeMinOutliers, timeMaxOutliers)
        outliers = math.or(outliers, distMinOutliers);
        outliers = math.or(outliers, distMaxOutliers);
        var filteredData = [];
        for (var i=0; i<data.length; i += 1) {
            if (!outliers[i]) {
                filteredData.push(data[i]);
            } else {
                console.log("Removed outlier");
            };
        };
        return filteredData;
    }

    var getTimes = function (data) {
        var times = [];
        for (var i=0; i < data.length; i += 1) {
            times.push(data[i]['duration']);
        }
        return times;
    };

    var distance = function (pt1, pt2) {
        return math.norm([pt2[0] - pt1[0], pt2[1] - pt1[1]]);
    };

    var getDistances = function (data) {
        var distances = [];
        for (var i=0; i < data.length; i += 1) {
            distances.push(distance(data[i].endXY, data[i].startXY));
        };
        return distances;
    };

    var finishAnalysis = function () {
        var MTs = [];
        var IDes = [];

        var data;
        for (var i=0; i<dataSets.length; i += 1) {
            data = removeOutliers(dataSets[i]);

            var directionalErrors = [];
            for (var j=0; j<data.length; j +=1) {
               var Vse = [ data[j].endXY[0] - data[j].startXY[0], data[j].endXY[1] - data[j].startXY[1] ];
               var Vsg = [ data[j].goalXY[0] - data[j].startXY[0], data[j].goalXY[1] - data[j].startXY[1] ];
               var err = ( ( math.dot(Vse, Vsg) / math.dot(Vsg, Vsg) ) * math.norm(Vsg) ) - math.norm(Vsg);
               directionalErrors.push(err);
            }
            var We = 4.133*math.std(directionalErrors);
            var dists = getDistances(data);
            var De = math.mean(dists);
            var IDe = math.log((De/We)+1 , 2);
            IDes.push(IDe);
            var times = getTimes(data);
            var MT = math.mean(times);
            MTs.push(MT);
        }
        var fittsCoefficients = leastSquares(IDes, MTs);
        var a = math.round(fittsCoefficients.intercept, 4);
        var b = math.round(fittsCoefficients.slope, 4);
        console.log(fittsCoefficients);
        displayResults(a, b, dataSets);
    };

    var displayResults = function (a, b, dataSets) {
        var html = "";
//        html += "<p>Fitts Law Model: MT = " + a.toString() + " + " + b.toString() + " x IDe</p>";
        html += "<h2>Please click below to download your results, and e-mail them back to me!</h2>";
        var resultURL = makeResultsFile(a, b, dataSets);
        var time = new Date();
        var dataFileName = "FittsLawResults-"+time.getDate()+'-'+time.getMonth()+'-'+time.getUTCFullYear()+'-'+time.getHours()+'-'+time.getMinutes()+'-'+time.getSeconds();
        $targetArea.css({'background-color':'LightGreen'}).html(html);
        var $downloadDiv = $('<a class="startButton" download="'+dataFileName+'">Download Results</a>').button().attr('href', resultURL).css({'bottom':'initial', 'top':'50%'}).css({'bottom':'initial', 'top':'50%'});
        $targetArea.append($downloadDiv)
    };

    var leastSquares = function (X,Y) {
        var sum_x = math.sum(X);
        var sum_y = math.sum(Y);
        var sum_xx = 0;
        var sum_xy = 0;
        var sum_yy = 0;
        var N = X.length;

        for (var i=0; i <N; i += 1) {
            sum_xx += X[i]*X[i];
            sum_xy += X[i]*Y[i];
            sum_yy += Y[i]*Y[i];
        };
        var slope = (N*sum_xy - sum_x*sum_y) / (N*sum_xx - sum_x*sum_x)
        var intercept = (sum_y/N) - (slope * sum_x)/N;
        return {slope:slope, intercept:intercept};
    };

    var resultsFile = null;
    var makeResultsFile = function (a, b, dataSets) {
        data = {'a': a,
                'b': b,
                'dwellTime': dwellTime,
                'startTime': startTime,
                'endTime': endTime,
                'setParameters': setParameters,
                'dataSets': dataSets}
        var contents = new Blob([JSON.stringify(data)], {type:'text/plain'});
        if (resultsFile !== null) {
            window.URL.revokeObjectURL(resultsFile);
        };
        resultsFile = window.URL.createObjectURL(contents);
        return resultsFile;
    };

};
