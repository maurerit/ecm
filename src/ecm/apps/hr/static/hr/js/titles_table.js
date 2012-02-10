// disable multi column sorting
$('#titles_table thead th').click(function(event) {
    if (!$(event.target).hasClass('sorthandle')) {
        event.shiftKey = false;
    }
});

// dataTable setup
$(document).ready(function() {
  table = $('#titles_table').dataTable( {
    bProcessing: true,
    bServerSide: true,
        bAutoWidth: false,
        iDisplayLength: 25,
    sAjaxSource: "/hr/titles/data/",
        sDom: 'rt',
        aoColumns: [
            { sTitle: "Title Name",    sWidth: "40%", sType: "html" },
            { sTitle: "Access Level",  sWidth: "20%", sType: "numeric", bSearchable: false   },
            { sTitle: "Members",       sWidth: "10%", sType: "html",    bSearchable: false, bSortable: false },
            { sTitle: "Role Count",    sWidth: "10%", sType: "numeric", bSearchable: false, bSortable: false },
            { sTitle: "Last Modified", sWidth: "20%", sType: "string",  bSearchable: false, bSortable: false }
        ],
        fnRowCallback: function( nRow, aData, iDisplayIndex, iDisplayIndexFull ) {
            /* apply color to all access level cells */
            accessLvl = aData[1];
            $('td:eq(1)', nRow).addClass("row-" + getAccessColor(accessLvl, COLOR_THRESHOLDS));
            return nRow;
    }
    } );

} );