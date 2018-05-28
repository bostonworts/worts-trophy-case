require "rails_helper"

describe "submit trophy" do
  it "succeeds with required fields after logging in via email" do
    worts_member = create(:user)
    competition = create(:competition)
    login_as(worts_member)

    fill_required_fields(competition: competition)
    click_on "Create Trophy"

    expect(current_path).to eq("/")

    # Brewer should be in the trophy list now
    expect(page).to have_content(worts_member.full_name)
  end

  it "succeeds when filling in optional fields" do
    worts_member = create(:user)
    competition = create(:competition)
    login_as(worts_member)

    fill_required_fields(competition: competition)
    fill_in :trophy_recipe_url, with: "https://iancanderson.com/brewlog/batches/001"
    select 2, from: :trophy_place
    select "Best Of Show", from: :trophy_place_context
    click_on "Create Trophy"

    expect(current_path).to eq("/")

    # Brewer should be in the trophy list now
    expect(page).to have_content(worts_member.full_name)
  end

  it "succeeds when attaching an image" do
    worts_member = create(:user)
    competition = create(:competition)
    login_as(worts_member)

    fill_required_fields(competition: competition)
    attach_file("trophy_photo", "spec/fixture_images/blueribbon.png")

    click_on "Create Trophy"

    expect(current_path).to eq("/")

    expect(page).to have_content(worts_member.full_name)
    expect(page).to have_css("a svg.octicon-file-media")
  end

  def fill_required_fields(competition:)
    select "3B - Czech Premium Pale Lager", from: :trophy_subcategory_id
    select 25, from: :trophy_bjcp_score
    select competition.description, from: :trophy_competition_id
  end
end
