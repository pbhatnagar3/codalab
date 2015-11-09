/** @jsx React.DOM */

// Display a worksheet item which is an image file in a bundle.
var ImageBundle = React.createClass({
    mixins: [CheckboxMixin, GoToBundleMixin],
    getInitialState: function() {
        this.props.item.state.checked = false;
        return this.props.item.state;
    },
    handleClick: function(event) {
        this.props.setFocus(this.props.index);
    },
    render: function() {
        var className = 'type-image' + (this.props.focused ? ' focused' : '');
        var checkbox = this.props.canEdit ? <input type="checkbox" className="ws-checkbox" onChange={this.handleCheck} checked={this.state.checked} disabled={!this.props.checkboxEnabled}/> : null;
        var src= "data:image/png;base64," + this.props.item.state.interpreted;
        var styles = {};
        if (this.state.properties) {
            if (this.state.properties.hasOwnProperty('height')) {
                styles['height'] = this.state.properties.height + "px;"
            }
            if (this.state.properties.hasOwnProperty('width')) {
                styles['width'] = this.state.properties.width + "px;"
            }
        }
        return(
            <div className="ws-item" onClick={this.handleClick}>
                {checkbox}
                <div className={className} ref={this.props.item.state.ref}>
                    <img style={styles} src={src} />
                </div>
            </div>
        );
    } // end of render function
}); //end of  ContentsBundle
