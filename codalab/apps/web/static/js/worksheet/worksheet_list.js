/** @jsx React.DOM */
/*
Displays a list of worksheets with a search bar.
TODO: this is currently not exposed in the interface.
In the future, should morph this into a search results page.
The search should adaptively load worksheets instead of loading them all.
*/

// key mapping for convenience. we can move this into the global scope at some point.
var keyMap = {
    13: "enter",
    38: "up",
    40: "down",
    74: "j",
    75: "k",
    88: "x",
    191: "fslash"
};

var Worksheets = React.createClass({
    // this is the master parent component -- the 'app'
    getInitialState: function(){
        return {
            activeComponent:"list",
            filter: "",
        }
    },
    handleFocus: function(event){
        // the search input is the only one who calls this so far.
        // if it's being focused, set it as the active component. if blurred, set the list as active.
        if(event.type=="focus"){
            this.setState({activeComponent:"search"});
        }else if(event.type=="blur"){
            this.setState({activeComponent:"list"});
        }
    },
    bindEvents: function(){
        // listen for ALL keyboard events at the top leve
        window.addEventListener('keydown', this.handleKeydown);
    },
    unbindEvents: function(){
        window.removeEventListener('keydown', this.handleKeydown);
    },
    setFilter: function(event){
        // all this does is store and update the string we're filter worksheet names by
        this.setState({filter:event.target.value})
    },
    handleKeydown: function(event){
        // the only key this guy cares about is \, because that's the shortcut to focus on the search bar
        if(keyMap[event.keyCode] == 'fslash'){
            event.preventDefault();
            $('html,body').animate({scrollTop: 0}, 250);
            this.refs.search.getDOMNode().focus();
        }
        // otherwise, try to pass off the event to the active component
        var activeComponent = this.refs[this.state.activeComponent];
        if(activeComponent.hasOwnProperty('handleKeydown')){
            // if it has a method to handle keyboard shortcuts, pass it
            activeComponent.handleKeydown(event);
        }else {
            // otherwise watch it go by
            return true;
        }
    },
    componentDidMount: function(){
        this.bindEvents();
    },
    componentWillUnmount: function(){
        this.unbindEvents();
    },
    render: function(){
        return(
            <div>
                <WorksheetSearch setFilter={this.setFilter} handleFocus={this.handleFocus} ref={"search"} active={this.state.activeComponent=='search'} />
                <WorksheetList handleFocus={this.handleFocus} ref={"list"} active={this.state.activeComponent=='list'} filter={this.state.filter} />
            </div>
        )
    }
});

////////////////////////////////////////////////////////////

var WorksheetList = React.createClass({
    getInitialState: function(){
        return {
            worksheets: [],
            focusIndex: 0,
            myWorksheets: false
        };
    },
    fetchWorksheetList: function(focusIndex){
        // get the list of worksheets and store it in this.state.worksheets
        $.ajax({
            type: "GET",
            url: "/api/worksheets",
            dataType: 'json',
            cache: false,
            success: function(data) {
                if(this.isMounted()){
                    this.setState({
                        worksheets: data
                    });
                }
                $("#worksheet-message").hide().removeClass('alert-box alert');
            }.bind(this),
            error: function(xhr, status, err) {
                console.error(this.props.url, status, err.toString());
                $("#worksheet-message").html("Couldn\'t retrieve worksheets. Please try refreshing the page.").addClass('alert-box alert');
                $("#container").hide();
            }.bind(this)
        });
    },
    componentDidMount: function() {
        this.fetchWorksheetList();
    },
    goToFocusedWorksheet: function(){
        // navigate to the worksheet details page for the focused worksheet
        var ws = this.refs['ws' + this.state.focusIndex]
        var ws_url = '/worksheets/' + ws.props.details.uuid + '/';
        window.open(ws_url);
    },
    toggleMyWorksheets: function(){
        // filter by MY worksheets?
        this.setState({myWorksheets: !this.state.myWorksheets});
    },
    deleteWorksheet: function(worksheet){
        var postdata = {
            'worksheet_uuid': worksheet.props.details.uuid
        }
        var deleteFocused = worksheet.props.focused;
        var currentFocused = this.state.focusIndex;
        if(currentFocused === this.state.worksheets.length - 1){
            currentFocused = this.state.worksheets.length - 2;
        }
        var self = this;
        $.ajax({
            type:'POST',
            cache: false,
            url:'/api/worksheets/delete/',
            contentType:"application/json; charset=utf-8",
            dataType: 'json',
            data: JSON.stringify(postdata),
            success: function(data, status, jqXHR){
                self.fetchWorksheetList(currentFocused);
            },
            error: function (data) {
                console.error(data);
            }
        });
    },
    handleKeydown: function(event) {
        // this guy has shortcuts for going up and down, and selecting (essentially, clicking on it)
        var key = keyMap[event.keyCode];
        if(typeof key !== 'undefined'){
            event.preventDefault();
            if(key == 'k' || key == 'up'){
                var newFI = Math.max(this.state.focusIndex - 1, 0);
                this.setState({focusIndex: newFI});
                this.scrollToItem(newFI);
            }else if (key == 'j' || key == 'down'){
                var newFI = Math.min(this.state.focusIndex + 1, this.state.worksheets.length - 1);
                this.setState({focusIndex: newFI});
                this.scrollToItem(newFI);
            }else if (key == 'x' || key == 'enter'){
                this.goToFocusedWorksheet();
            }else {
                return false;
            }
        }
    },
    filterWorksheets:function(filter){
        // internal method for filtering the list, called from render() below
        var worksheets = this.state.worksheets;
        if(this.state.myWorksheets){
            worksheets = worksheets.filter(function(ws){ return String(ws.owner_id) === String(user_id) });
        }
        if(this.props.filter.length){
            console.log('filtering by: ' + filter);
            worksheets = worksheets.filter(function(ws){
                return (ws.name.indexOf(filter) > -1);
            });
        }
        return worksheets;
    },
    scrollToItem: function(index){
        if(this.state.worksheets.length){
            // scroll the window to keep the focused element in view
            var itemNode = this.refs['ws' + index].getDOMNode();
            $('html,body').animate({scrollTop: itemNode.offsetTop - 100}, 250);
            return false;
        }
    },
    render: function() {
        // filter the worksheets by whatever
        var worksheets = this.filterWorksheets(this.props.filter);
        // if there's only one worksheet, it should always be focused
        var focusIndex = worksheets.length > 1 ? this.state.focusIndex : 0;
        var self = this;
        if(worksheets.length){
            var worksheetList = worksheets.map(function(worksheet, index){
                var wsID = 'ws' + index;
                var focused = focusIndex === index;
                return <Worksheet details={worksheet} focused={focused} ref={wsID} key={index} deleteWorksheet={self.deleteWorksheet} />
            });
        } else {
            worksheetList = 'No worksheets matched your criteria'
        }

        myWorksheetCheckbox = '';
        if(CODAUSER.is_authenticated){
            myWorksheetCheckbox = (
                    <label className="my-worksheets-toggle">
                        <input type="checkbox" tabIndex="-1" onChange={this.toggleMyWorksheets} checked={this.state.myWorksheets} />
                        Show my worksheets only
                    </label>
                )
        }
        return (
            <div id="worksheet-list">
                <div className="checkbox">
                    {myWorksheetCheckbox}
                </div>
                {worksheetList}
            </div>
        );
    }
});

var Worksheet = React.createClass({
    // a single worksheet in the list
    getInitialState: function(){
        return {
            display: true
        }
    },
    handleDelete: function(){
        if(window.confirm('Are you sure you want to permanently delete this worksheet?')){
            this.setState({ display:false });
            this.props.deleteWorksheet(this);
        }else {
            return false;
        }
    },
    render: function(){
        var ws = this.props.details;
        var ws_url = '/worksheets/' + this.props.details.uuid + '/';
        var focused = this.props.focused ? ' focused' : '';
        var classString = 'worksheet-tile' + focused;
        var byline = '';
        if (ws.owner_name) {
            byline += 'by ' + ws.owner_name;
            if(ws.permission == 1){
                byline += ' (read-only)';
            }
        }
        if(this.state.display){
            return (
                <div className={classString}>
                    <div className="worksheet-inner">
                        <h3><a href={ws_url} target="_blank">{ws.name}</a></h3>
                        <div className="byline">{byline}</div>
                        <button type="button" onClick={this.handleDelete} className="btn btn-link btn-sm delete-worksheet">Delete</button>
                    </div>
                </div>
            );
        }else {
            return (
                <div></div>
            )
        }
    }
});

////////////////////////////////////////////////////////////

var WorksheetSearch = React.createClass({
    // the search bar at the top. it only does three things, all of them in the parent's state:
    //   1. if it's focused, make it the active component
    //   2. if it's blurred, make the other component active
    //   3. pass the value of the input up to the parent to use for filtering
    render: function(){
        return (
            <input id="search" className="ws-search form-control" type="text" placeholder="Search worksheets" onChange={this.props.setFilter} onFocus={this.props.handleFocus} onBlur={this.props.handleFocus}/>
        )
    }
});

React.render(<Worksheets />, document.getElementById('ws_list_container'));
